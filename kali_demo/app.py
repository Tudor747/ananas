"""Local browser application for safe Level 1 discovery on Kali Linux."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pi_ot_probe.core.models import Scan, ScanLevel, ScanProfile
from pi_ot_probe.database.repository import Repository
from pi_ot_probe.scanners.base import CancellationToken
from pi_ot_probe.scanners.orchestrator import ScanOrchestrator
from kali_demo.real_scanner import (
    NmapDiscoveryScanner,
    discover_local_networks,
    validate_target,
)


DEMO_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE = DEMO_DIR / "data" / "demo.db"


class RealRunRequest(BaseModel):
    target: str
    authorized: bool


class DemoService:
    """Coordinates synthetic scans and prepares dashboard-friendly records."""

    def __init__(self, database_path: Path | str) -> None:
        self.repository = Repository(database_path)
        self._scan_lock = asyncio.Lock()
        self._active_token: CancellationToken | None = None
        self._active_scanner: NmapDiscoveryScanner | None = None

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
            scan = Scan(
                site=f"KALI_REAL_{str(network).replace('/', '_')}",
                level=ScanLevel.DISCOVERY,
                profile=ScanProfile.INDUSTRIAL,
                target=str(network),
                simulation=False,
                authorized=True,
            )
            try:
                outcome = await ScanOrchestrator(self.repository).run(
                    scan=scan,
                    scanner=scanner,
                    cancellation=token,
                )
            finally:
                self._active_token = None
                self._active_scanner = None
            return {
                "scan_id": outcome.scan.id,
                "status": outcome.scan.status.value,
                "target": str(network),
                "assets": len(outcome.assets),
                "findings": len(outcome.findings),
                "cancelled": outcome.scan.cancelled,
            }

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
                """SELECT a.id, a.ip, a.mac, a.hostname, a.vendor, a.device_type,
                    a.criticality, a.confidence, a.risk_score, a.source, a.last_seen,
                    COALESCE((SELECT GROUP_CONCAT(port, ', ') FROM
                        (SELECT port FROM ports WHERE asset_id=a.id ORDER BY port)), '') AS ports,
                    COALESCE((SELECT GROUP_CONCAT(name, ', ') FROM
                        (SELECT name FROM protocols WHERE asset_id=a.id ORDER BY name)), '') AS protocols
                FROM assets a WHERE a.site_id=?
                ORDER BY a.risk_score DESC, a.ip""",
                (site_id,),
            ).fetchall()]
            findings = [dict(row) for row in connection.execute(
                """SELECT title, asset, severity, risk_score, confidence,
                    technical_reason, human_explanation, recommendation, evidence, created_at
                FROM findings f JOIN scans sc ON sc.id=f.scan_id
                WHERE sc.site_id=? ORDER BY created_at DESC LIMIT 20""",
                (site_id,),
            ).fetchall()]
            changes = [dict(row) for row in connection.execute(
                """SELECT change_type, asset_identity, details_json, detected_at
                FROM changes WHERE site_id=? ORDER BY detected_at DESC LIMIT 20""",
                (site_id,),
            ).fetchall()]
            access_points = [dict(row) for row in connection.execute(
                """SELECT ssid, bssid, signal_dbm, channel, encryption, last_seen
                FROM wifi_access_points WHERE site_id=?
                ORDER BY last_seen DESC, signal_dbm DESC""",
                (site_id,),
            ).fetchall()]
            scans = [dict(row) for row in connection.execute(
                """SELECT id, status, profile, level, assets_found, findings_found,
                    started_at, finished_at FROM scans ORDER BY started_at DESC LIMIT 10"""
            ).fetchall()]
            counts = {
                "sites": 1 if current_site else 0,
                "scans": int(connection.execute(
                    "SELECT COUNT(*) FROM scans WHERE site_id=?", (site_id,)
                ).fetchone()[0]),
                "assets": int(connection.execute(
                    "SELECT COUNT(*) FROM assets WHERE site_id=?", (site_id,)
                ).fetchone()[0]),
                "findings": int(connection.execute(
                    """SELECT COUNT(*) FROM findings f JOIN scans sc ON sc.id=f.scan_id
                    WHERE sc.site_id=?""", (site_id,)
                ).fetchone()[0]),
                "audit_log": int(connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]),
            }
        for change in changes:
            raw_details = change.pop("details_json", "{}")
            try:
                change["summary"] = json.loads(str(raw_details)).get("summary", "")
            except (json.JSONDecodeError, AttributeError):
                change["summary"] = ""
        return {
            "mode": (
                "simulation" if current_site and current_site["simulation"]
                else "real_discovery" if current_site else "ready"
            ),
            "network_traffic": bool(current_site and not current_site["simulation"]),
            "current_site": current_site["name"] if current_site else None,
            "counts": counts,
            "assets": assets,
            "findings": findings,
            "changes": changes,
            "access_points": access_points,
            "scans": scans,
        }


def create_app(database_path: Path | str = DEFAULT_DATABASE) -> FastAPI:
    service = DemoService(database_path)
    application = FastAPI(
        title="Pi-OT Probe Kali Discovery",
        description="Local, explicitly authorized, rate-limited host discovery dashboard.",
        version="0.1.0",
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

    @application.post("/api/cancel")
    async def cancel() -> dict[str, object]:
        return {"cancel_requested": service.cancel()}

    return application


database = Path(os.getenv("PI_OT_DEMO_DATABASE", str(DEFAULT_DATABASE)))
app = create_app(database)
