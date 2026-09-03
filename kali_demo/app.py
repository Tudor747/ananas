"""Cross-platform browser application for safe V2/V3 network assessment."""

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
from pydantic import BaseModel

from pi_ot_probe.core.models import Asset, Scan, ScanLevel, ScanProfile, Service
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


DEMO_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE = DEMO_DIR / "data" / "demo.db"


class RealRunRequest(BaseModel):
    target: str
    authorized: bool


class VerifyRequest(BaseModel):
    host: str
    authorized: bool


class WifiRequest(BaseModel):
    authorized: bool


class BaselineRequest(BaseModel):
    name: str = "Site baseline"


class WebRequest(BaseModel):
    host: str
    port: int
    scheme: str
    authorized: bool


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
                )
                changes = self.baselines.compare(scan.site, scan.id)
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

    def _load_current_asset(self, host: str) -> tuple[str, Asset]:
        self.repository.initialize()
        with self.repository.connect() as connection:
            current_site = connection.execute(
                """SELECT s.id, s.name FROM scans sc JOIN sites s ON s.id=sc.site_id
                ORDER BY sc.rowid DESC LIMIT 1"""
            ).fetchone()
            if not current_site:
                raise ValueError("run host discovery before verifying a device")
            row = connection.execute(
                "SELECT * FROM assets WHERE site_id=? AND ip=?",
                (current_site["id"], host),
            ).fetchone()
            if not row:
                raise ValueError("select a device from the current asset inventory")
            ports = [int(item[0]) for item in connection.execute(
                "SELECT port FROM ports WHERE asset_id=? ORDER BY port", (row["id"],)
            ).fetchall()]
            services = [Service(
                port=int(item["port"]), transport=item["transport"], name=item["name"],
                product=item["product"], version=item["version"], evidence=item["evidence"],
                state=item["state"], reason=item["reason"], method=item["method"],
                confidence=item["confidence"], extra_info=item["extra_info"],
                tunnel=item["tunnel"], cpes=json.loads(item["cpes_json"] or "[]"),
            ) for item in connection.execute(
                """SELECT port, transport, name, product, version, evidence, state,
                    reason, method, confidence, extra_info, tunnel, cpes_json
                FROM services WHERE asset_id=? ORDER BY port""", (row["id"],)
            ).fetchall()]
            asset = Asset(
                id=int(row["id"]), ip=row["ip"], mac=row["mac"], hostname=row["hostname"],
                vendor=row["vendor"], device_type=row["device_type"], ports=ports,
                services=services, first_seen=datetime.fromisoformat(row["first_seen"]),
                last_seen=datetime.fromisoformat(row["last_seen"]), risk_score=int(row["risk_score"]),
                criticality=row["criticality"], confidence=float(row["confidence"]), source=row["source"],
                status=row["status"], discovery_reason=row["discovery_reason"],
                hostnames=json.loads(row["hostnames_json"] or "[]"),
            )
            return str(current_site["name"]), asset

    async def verify_services(self, host: str, authorized: bool) -> dict[str, object]:
        if not authorized:
            raise PermissionError("confirm authorization before service verification")
        if self._scan_lock.locked():
            raise RuntimeError("another scan is already running")
        site, asset = self._load_current_asset(host)
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
                now = datetime.now().astimezone()
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
                observed_at = datetime.now().astimezone().isoformat()
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

    def cancel(self) -> bool:
        if not self._active_token or not self._active_scanner:
            return False
        self._active_token.cancel()
        self._active_scanner.cancel()
        return True

    def state(self) -> dict[str, object]:
        self.repository.initialize()
        with self.repository.connect() as connection:
            current_site = connection.execute(
                """SELECT s.id, s.name, sc.simulation FROM scans sc JOIN sites s ON s.id=sc.site_id
                ORDER BY sc.rowid DESC LIMIT 1"""
            ).fetchone()
            site_id = int(current_site["id"]) if current_site else -1
            assets = [dict(row) for row in connection.execute(
                """SELECT a.id, a.ip, a.mac, a.hostname, a.vendor, a.source,
                    a.status, a.discovery_reason, a.hostnames_json,
                    a.first_seen, a.last_seen
                FROM assets a WHERE a.site_id=? ORDER BY a.ip""", (site_id,)
            ).fetchall()]
            for asset in assets:
                asset_id = int(asset["id"])
                try:
                    asset["hostnames"] = json.loads(asset.pop("hostnames_json") or "[]")
                except (json.JSONDecodeError, TypeError):
                    asset["hostnames"] = []
                asset["ports"] = [dict(row) for row in connection.execute(
                    """SELECT port, transport, state, observed_at FROM ports
                    WHERE asset_id=? ORDER BY port, transport""", (asset_id,)
                ).fetchall()]
                asset["services"] = [dict(row) for row in connection.execute(
                    """SELECT port, transport, state, reason, name, product, version,
                        extra_info, tunnel, method, confidence, cpes_json, evidence, observed_at
                    FROM services WHERE asset_id=? ORDER BY port, transport""", (asset_id,)
                ).fetchall()]
                for service in asset["services"]:
                    try:
                        service["cpes"] = json.loads(service.pop("cpes_json") or "[]")
                    except (json.JSONDecodeError, TypeError):
                        service["cpes"] = []
                asset["protocols"] = [dict(row) for row in connection.execute(
                    """SELECT name, port, evidence, observed_at FROM protocols
                    WHERE asset_id=? ORDER BY name, port""", (asset_id,)
                ).fetchall()]
                asset["web_observations"] = [dict(row) for row in connection.execute(
                    """SELECT id, scheme, host, port, requested_path AS path, status_code,
                        status_reason, http_version, headers_json, tls_json, observed_at
                    FROM web_observations WHERE asset_id=? ORDER BY observed_at DESC LIMIT 10""",
                    (asset_id,),
                ).fetchall()]
                for observation in asset["web_observations"]:
                    observation["headers"] = json.loads(observation.pop("headers_json") or "[]")
                    observation["tls"] = (
                        json.loads(observation.pop("tls_json"))
                        if observation.get("tls_json") else None
                    )
            changes = [dict(row) for row in connection.execute(
                """SELECT id, change_type, asset_identity, details_json, detected_at, acknowledged_at
                FROM changes WHERE site_id=? ORDER BY detected_at DESC LIMIT 20""",
                (site_id,),
            ).fetchall()]
            access_points = [dict(row) for row in connection.execute(
                """SELECT ssid, bssid, signal_dbm AS signal_dbm_estimated, signal_percent, channel,
                    frequency_mhz, band, authentication, encryption, cipher, radio_type,
                    network_type, mode, rate, source, first_seen, last_seen
                FROM wifi_access_points WHERE site_id=?
                ORDER BY last_seen DESC, signal_dbm DESC""",
                (site_id,),
            ).fetchall()]
            scans = [dict(row) for row in connection.execute(
                """SELECT id, status, target, level, assets_found,
                    started_at, finished_at, cancelled, error FROM scans WHERE site_id=?
                    ORDER BY started_at DESC LIMIT 10""", (site_id,)
            ).fetchall()]
            counts = {
                "sites": 1 if current_site else 0,
                "scans": int(connection.execute(
                    "SELECT COUNT(*) FROM scans WHERE site_id=?", (site_id,)
                ).fetchone()[0]),
                "assets": int(connection.execute(
                    "SELECT COUNT(*) FROM assets WHERE site_id=?", (site_id,)
                ).fetchone()[0]),
                "audit_log": int(connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]),
                "changes": int(connection.execute(
                    "SELECT COUNT(*) FROM changes WHERE site_id=?", (site_id,)
                ).fetchone()[0]),
                "access_points": int(connection.execute(
                    "SELECT COUNT(*) FROM wifi_access_points WHERE site_id=?", (site_id,)
                ).fetchone()[0]),
            }
        for change in changes:
            raw_details = change.pop("details_json", "{}")
            try:
                details = json.loads(str(raw_details))
                change["summary"] = details.get("summary", "")
                change["details"] = details
            except (json.JSONDecodeError, AttributeError):
                change["summary"] = ""
                change["details"] = {}
        site_name = str(current_site["name"]) if current_site else None
        return {
            "mode": (
                "simulation" if current_site and current_site["simulation"]
                else "real_discovery" if current_site else "ready"
            ),
            "network_traffic": bool(current_site and not current_site["simulation"]),
            "current_site": site_name,
            "counts": counts,
            "operation": dict(self._operation),
            "baseline": self.baselines.status(site_name),
            "assets": assets,
            "changes": changes,
            "access_points": access_points,
            "scans": scans,
        }


def create_app(database_path: Path | str = DEFAULT_DATABASE) -> FastAPI:
    service = DemoService(database_path)
    application = FastAPI(
        title="Pi-OT Probe Engineering Console",
        description="Local V2/V3 discovery, service verification, baseline, and reporting dashboard.",
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

    @application.post("/api/real/run")
    async def run_real(request: RealRunRequest) -> dict[str, object]:
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
    async def verify_services(request: VerifyRequest) -> dict[str, object]:
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
    async def refresh_wifi(request: WifiRequest) -> dict[str, object]:
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
    async def inspect_web(request: WebRequest) -> dict[str, object]:
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

    return application


database = Path(os.getenv("PI_OT_DEMO_DATABASE", str(DEFAULT_DATABASE)))
app = create_app(database)
