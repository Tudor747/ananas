"""Coordinate real inventory operations independently of HTTP routes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pi_ot_probe.domain.models import Scan, ScanLevel, ScanProfile, utc_now
from pi_ot_probe.database.repository import Repository
from pi_ot_probe.database.current_asset import load_current_asset
from pi_ot_probe.scanners.base import CancellationToken
from pi_ot_probe.scanners.orchestrator import ScanOrchestrator
from pi_ot_probe.collectors.nmap import NmapDiscoveryScanner, NmapServiceScanner
from pi_ot_probe.collectors.interfaces import discover_local_networks
from pi_ot_probe.collectors.targets import validate_target
from pi_ot_probe.application.baselines import BaselineManager
from pi_ot_probe.collectors.wifi import discover_wifi
from pi_ot_probe.collectors.http import inspect_website
from pi_ot_probe.application.dashboard import build_dashboard_state
from pi_ot_probe.application.instruments import InstrumentWorkspace


class ProbeService:
    """Coordinates bounded real scans and prepares dashboard-friendly records."""

    def __init__(self, database_path: Path | str) -> None:
        self.repository = Repository(database_path)
        self.baselines = BaselineManager(self.repository)
        self.instruments = InstrumentWorkspace(self.repository)
        # Serialize operations so their progress and cancellation cannot overlap.
        self._scan_lock = asyncio.Lock()
        self._active_token: CancellationToken | None = None
        self._active_scanner: NmapDiscoveryScanner | NmapServiceScanner | None = None
        self._operation: dict[str, object] = {
            "status": "idle", "kind": None, "target": None, "completed": 0, "total": 0,
        }

    async def networks(self) -> dict[str, object]:
        networks = await discover_local_networks()
        return {
            "nmap_available": NmapDiscoveryScanner.available(),
            "networks": [network.to_dict() for network in networks],
        }

    async def run_real(self, target: str, authorized: bool) -> dict[str, object]:
        if not authorized:
            raise PermissionError("confirm that you are authorized to assess this network")
        if self._scan_lock.locked():
            raise RuntimeError("a discovery scan is already running")
        local_networks = await discover_local_networks()
        network = validate_target(target, local_networks)
        scanner = NmapDiscoveryScanner(network)
        if not scanner.available():
            raise RuntimeError("Nmap is not installed or discoverable; see docs/usage.md for setup")
        async with self._scan_lock:
            token = CancellationToken()
            self._active_token = token
            self._active_scanner = scanner
            self._operation = {
                "status": "running", "kind": "host_discovery", "target": str(network),
                "completed": 0, "total": int(network.num_addresses),
            }
            scan = Scan(
                site=f"KALI_REAL_{str(network).replace('/', '_')}",
                level=ScanLevel.DISCOVERY,
                profile=ScanProfile.INDUSTRIAL,
                target=str(network),
                simulation=False,
                authorized=True,
            )
            def progress(update: Any) -> None:
                self._operation.update(
                    completed=update.completed, total=update.total, message=update.message
                )
            try:
                outcome = await ScanOrchestrator(self.repository, analyze_risk=False).run(
                    scan=scan,
                    scanner=scanner,
                    cancellation=token,
                    on_progress=progress,
                    user_action="host_discovery",
                )
                changes = (
                    self.baselines.compare(scan.site, scan.id)
                    if outcome.scan.status.value == "completed" else []
                )
                self._operation.update(status=outcome.scan.status.value)
            except Exception:
                self._operation.update(status="failed")
                raise
            finally:
                self._active_token = None
                self._active_scanner = None
            return {
                "scan_id": outcome.scan.id,
                "status": outcome.scan.status.value,
                "target": str(network),
                "assets": len(outcome.assets),
                "cancelled": outcome.scan.cancelled,
                "changes": len(changes),
            }


    async def verify_services(self, host: str, authorized: bool) -> dict[str, object]:
        if not authorized:
            raise PermissionError("confirm authorization before service verification")
        if self._scan_lock.locked():
            raise RuntimeError("another scan is already running")
        site, asset = load_current_asset(self.repository, host, include_latest_verification=False)
        local_networks = await discover_local_networks()
        validate_target(f"{asset.ip}/32", local_networks)
        scanner = NmapServiceScanner(asset)
        async with self._scan_lock:
            token = CancellationToken()
            self._active_token = token
            self._active_scanner = scanner
            self._operation = {
                "status": "running", "kind": "service_verification", "target": asset.ip,
                "completed": 0, "total": 1,
            }
            scan = Scan(
                site=site, level=ScanLevel.VERIFY, profile=ScanProfile.INDUSTRIAL,
                target=asset.ip, simulation=False, authorized=True,
            )
            try:
                outcome = await ScanOrchestrator(self.repository, analyze_risk=False).run(
                    scan=scan, scanner=scanner, cancellation=token,
                    on_progress=lambda update: self._operation.update(
                        completed=update.completed, total=update.total, message=update.message
                    ),
                    user_action="service_verification",
                )
                changes = (
                    self.baselines.compare(site, scan.id)
                    if outcome.scan.status.value == "completed" else []
                )
                self._operation.update(status=outcome.scan.status.value)
            except Exception:
                self._operation.update(status="failed")
                raise
            finally:
                self._active_token = None
                self._active_scanner = None
        verified = outcome.assets[0] if outcome.assets else asset
        return {
            "scan_id": outcome.scan.id,
            "status": outcome.scan.status.value,
            "host": asset.ip,
            "open_ports": verified.ports,
            "cancelled": outcome.scan.cancelled,
            "changes": len(changes),
        }

    async def refresh_wifi(self, authorized: bool) -> dict[str, object]:
        if not authorized:
            raise PermissionError("confirm authorization before Wi-Fi inventory")
        if self._scan_lock.locked():
            raise RuntimeError("another scan is already running")
        state = self.state()
        site = state.get("current_site")
        if not site:
            raise ValueError("run host discovery before collecting Wi-Fi inventory")
        async with self._scan_lock:
            self._operation = {
                "status": "running", "kind": "wifi_inventory", "target": site,
                "completed": 0, "total": 1,
            }
            try:
                access_points = await discover_wifi()
                now = utc_now()
                with self.repository.connect() as connection:
                    row = connection.execute("SELECT id FROM sites WHERE name=?", (site,)).fetchone()
                    assert row is not None
                    site_id = int(row["id"])
                for access_point in access_points:
                    self.repository.upsert_access_point(site_id, access_point, now)
                changes = self.baselines.compare_latest(str(site)) if self.baselines.status(str(site)) else []
                self._operation.update(status="completed", completed=1)
            except Exception:
                self._operation.update(status="failed")
                raise
        return {"access_points": len(access_points), "changes": len(changes)}

    async def inspect_web(
        self, host: str, port: int, scheme: str, authorized: bool
    ) -> dict[str, object]:
        if not authorized:
            raise PermissionError("confirm authorization before inspecting a web service")
        if self._scan_lock.locked():
            raise RuntimeError("another operation is already running")
        _, asset = load_current_asset(self.repository, host)
        if port not in asset.ports:
            raise ValueError("inspect only a port previously observed as open on this device")
        local_networks = await discover_local_networks()
        validate_target(f"{asset.ip}/32", local_networks)
        normalized_scheme = scheme.lower()
        if normalized_scheme not in {"http", "https"}:
            raise ValueError("scheme must be http or https")
        async with self._scan_lock:
            self._operation = {
                "status": "running", "kind": "web_inspection",
                "target": f"{normalized_scheme}://{asset.ip}:{port}/",
                "completed": 0, "total": 1,
            }
            try:
                observation = await inspect_website(asset.ip, port, normalized_scheme)
                observed_at = utc_now().isoformat()
                with self.repository.connect() as connection:
                    connection.execute(
                        """INSERT INTO web_observations(asset_id, scheme, host, port,
                        requested_path, status_code, status_reason, http_version,
                        headers_json, tls_json, observed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (asset.id, observation.scheme, observation.host, observation.port,
                         observation.path, observation.status_code, observation.status_reason,
                         observation.http_version, json.dumps(observation.headers),
                         json.dumps(observation.tls) if observation.tls else None, observed_at),
                    )
                self._operation.update(status="completed", completed=1)
            except Exception:
                self._operation.update(status="failed")
                raise
        return {**observation.to_dict(), "observed_at": observed_at}

    def create_baseline(self, name: str) -> dict[str, object]:
        site = self.state().get("current_site")
        if not site:
            raise ValueError("run host discovery before creating a baseline")
        return self.baselines.create(str(site), name)

    def acknowledge_change(self, change_id: int) -> bool:
        site = self.state().get("current_site")
        return bool(site and self.baselines.acknowledge(str(site), change_id))

    def triage_change(self, change_id: int, status: str, note: str) -> bool:
        site = self.state().get("current_site")
        return bool(site and self.baselines.triage(str(site), change_id, status, note))

    def cancel(self) -> bool:
        if not self._active_token or not self._active_scanner:
            return False
        self._active_token.cancel()
        self._active_scanner.cancel()
        return True

    def state(self) -> dict[str, object]:
        return build_dashboard_state(self.repository, self.baselines, self._operation)

    def assessment(self) -> dict[str, Any]:
        return self.instruments.assessment(self.state())

    def require_current_site(self, expected: str) -> dict[str, Any]:
        state = self.state()
        if not expected or state.get("current_site") != expected:
            raise ValueError("the current network changed or has not been discovered; refresh before saving")
        return state
