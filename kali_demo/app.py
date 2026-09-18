"""Cross-platform local application for bounded raw network observation."""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pi_ot_probe.core.models import Asset, Scan, ScanLevel, ScanProfile, Service, utc_now
from pi_ot_probe.database.repository import Repository
from pi_ot_probe.scanners.base import CancellationToken
from pi_ot_probe.scanners.orchestrator import ScanOrchestrator
from kali_demo.real_scanner import (
    NmapDiscoveryScanner,
    NmapServiceScanner,
    discover_local_networks,
    validate_target,
)
from kali_demo.baseline import BaselineManager
from kali_demo.reports import assets_csv, site_report
from kali_demo.wifi_inventory import discover_wifi
from kali_demo.web_inspector import inspect_website
from kali_demo.state_builder import build_dashboard_state
from kali_demo.contracts import (
    BaselineRequest,
    ChangeReviewRequest,
    DiscoveryRequest,
    ServiceVerificationRequest,
    WebsiteInspectionRequest,
    WifiInventoryRequest,
)
from kali_demo.scenarios import VALIDATION_SCENARIOS


DEMO_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE = DEMO_DIR / "data" / "demo.db"


class DemoService:
    """Coordinates bounded real scans and prepares dashboard-friendly records."""

    def __init__(self, database_path: Path | str) -> None:
        self.repository = Repository(database_path)
        self.baselines = BaselineManager(self.repository)
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
            raise RuntimeError("Nmap is not installed; run: sudo apt install nmap")
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

    def _load_current_asset(
        self, host: str, *, include_latest_verification: bool = True
    ) -> tuple[str, Asset]:
        """Load an asset from the latest successfully completed discovery."""
        self.repository.initialize()
        with self.repository.connect() as connection:
            discovery = connection.execute(
                """SELECT sc.id AS scan_id, sc.rowid AS scan_rowid,
                    sc.site_id, s.name
                FROM scans sc
                JOIN sites s ON s.id=sc.site_id
                WHERE sc.level=1 AND sc.status='completed'
                ORDER BY sc.rowid DESC LIMIT 1"""
            ).fetchone()
            if not discovery:
                raise ValueError("run host discovery before verifying a device")
            row = connection.execute(
                """SELECT a.*, sa.snapshot_json FROM assets a JOIN scan_assets sa
                ON sa.asset_id=a.id WHERE a.site_id=? AND a.ip=? AND sa.scan_id=?""",
                (discovery["site_id"], host, discovery["scan_id"]),
            ).fetchone()
            if not row:
                raise ValueError("select a device from the current asset inventory")
            try:
                observed = json.loads(row["snapshot_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                observed = {}
            ports: list[int] = []
            services: list[Service] = []
            if include_latest_verification:
                verification = connection.execute(
                    """SELECT sa.snapshot_json FROM scan_assets sa JOIN scans sc
                    ON sc.id=sa.scan_id WHERE sa.asset_id=? AND sc.site_id=? AND sc.level=2
                    AND sc.status='completed' AND sc.rowid>? ORDER BY sc.rowid DESC LIMIT 1""",
                    (row["id"], discovery["site_id"], discovery["scan_rowid"]),
                ).fetchone()
                if verification and verification["snapshot_json"]:
                    try:
                        verified = json.loads(verification["snapshot_json"])
                    except (json.JSONDecodeError, TypeError):
                        verified = {}
                    ports = [int(port) for port in verified.get("ports", [])]
                    services = [Service(**item) for item in verified.get("services", [])]
            asset = Asset(
                id=int(row["id"]), ip=observed.get("ip", row["ip"]),
                mac=observed.get("mac", row["mac"]),
                hostname=observed.get("hostname", row["hostname"]),
                vendor=observed.get("vendor", row["vendor"]),
                device_type=observed.get("device_type", row["device_type"]), ports=ports,
                services=services,
                first_seen=datetime.fromisoformat(observed.get("first_seen", row["first_seen"])),
                last_seen=datetime.fromisoformat(observed.get("last_seen", row["last_seen"])),
                risk_score=int(observed.get("risk_score", row["risk_score"])),
                criticality=observed.get("criticality", row["criticality"]),
                confidence=float(observed.get("confidence", row["confidence"])),
                source=observed.get("source", row["source"]),
                status=observed.get("status", row["status"]),
                discovery_reason=observed.get("discovery_reason", row["discovery_reason"]),
                hostnames=observed.get("hostnames", json.loads(row["hostnames_json"] or "[]")),
            )
            return str(discovery["name"]), asset

    async def verify_services(self, host: str, authorized: bool) -> dict[str, object]:
        if not authorized:
            raise PermissionError("confirm authorization before service verification")
        if self._scan_lock.locked():
            raise RuntimeError("another scan is already running")
        site, asset = self._load_current_asset(host, include_latest_verification=False)
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
        _, asset = self._load_current_asset(host)
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


def create_app(database_path: Path | str = DEFAULT_DATABASE) -> FastAPI:
    service = DemoService(database_path)
    application = FastAPI(
        title="Pi-OT Probe Engineering Console",
        description="Local discovery, verification, baseline, and raw evidence dashboard.",
        version="0.4.0",
    )
    application.state.demo_service = service
    application.mount("/static", StaticFiles(directory=DEMO_DIR / "static"), name="static")

    @application.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(DEMO_DIR / "static" / "index.html")

    @application.get("/api/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ready",
            "mode": "real_discovery",
            "network_traffic_when_scanning": True,
        }

    @application.get("/api/state")
    async def state() -> dict[str, object]:
        return service.state()

    @application.get("/api/networks")
    async def networks() -> dict[str, object]:
        try:
            return await service.networks()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.get("/api/validation/scenarios")
    async def validation_scenarios() -> dict[str, object]:
        return {"scenarios": list(VALIDATION_SCENARIOS)}

    @application.post("/api/real/run")
    async def run_real(request: DiscoveryRequest) -> dict[str, object]:
        try:
            return await service.run_real(request.target, request.authorized)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            status_code = 409 if "already running" in str(exc) else 503
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @application.post("/api/real/verify")
    async def verify_services(request: ServiceVerificationRequest) -> dict[str, object]:
        try:
            return await service.verify_services(request.host, request.authorized)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            status_code = 409 if "already running" in str(exc) else 503
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @application.post("/api/wifi/refresh")
    async def refresh_wifi(request: WifiInventoryRequest) -> dict[str, object]:
        try:
            return await service.refresh_wifi(request.authorized)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            status_code = 409 if "already running" in str(exc) else 503
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @application.post("/api/real/web")
    async def inspect_web(request: WebsiteInspectionRequest) -> dict[str, object]:
        try:
            return await service.inspect_web(
                request.host, request.port, request.scheme, request.authorized
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (RuntimeError, OSError, TimeoutError) as exc:
            status_code = 409 if "already running" in str(exc) else 503
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @application.post("/api/baseline")
    async def create_baseline(request: BaselineRequest) -> dict[str, object]:
        try:
            return service.create_baseline(request.name)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post("/api/changes/{change_id}/acknowledge")
    async def acknowledge_change(change_id: int) -> dict[str, object]:
        acknowledged = service.acknowledge_change(change_id)
        if not acknowledged:
            raise HTTPException(status_code=404, detail="change was not found")
        return {"acknowledged": True, "change_id": change_id}

    @application.post("/api/changes/{change_id}/triage")
    async def triage_change(change_id: int, request: ChangeReviewRequest) -> dict[str, object]:
        try:
            updated = service.triage_change(change_id, request.status, request.note)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not updated:
            raise HTTPException(status_code=404, detail="change was not found")
        return {"updated": True, "change_id": change_id, "status": request.status}

    @application.get("/api/reports/site.json")
    async def json_report() -> JSONResponse:
        return JSONResponse(site_report(service.state()), headers={
            "Content-Disposition": 'attachment; filename="pi-ot-site-report.json"'
        })

    @application.get("/api/reports/assets.csv")
    async def csv_report() -> Response:
        return Response(
            assets_csv(service.state()),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="pi-ot-assets.csv"'},
        )

    @application.post("/api/cancel")
    async def cancel() -> dict[str, object]:
        return {"cancel_requested": service.cancel()}

    @application.middleware("http")
    async def security_headers(request: Any, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    return application


database = Path(os.getenv("PI_OT_DEMO_DATABASE", str(DEFAULT_DATABASE)))
app = create_app(database)
