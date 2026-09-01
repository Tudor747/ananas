"""Browser demo for exercising Pi-OT Probe safely on Kali Linux.

Only the synthetic scanner is exposed. The application has no endpoint or
configuration option for real network targets.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pi_ot_probe.core.models import Scan, ScanLevel, ScanProfile
from pi_ot_probe.database.repository import Repository
from pi_ot_probe.scanners.base import CancellationToken
from pi_ot_probe.scanners.orchestrator import ScanOrchestrator
from pi_ot_probe.simulation.scanner import SimulationScanner


DEMO_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE = DEMO_DIR / "data" / "demo.db"


class RunRequest(BaseModel):
    scenario: Literal["baseline", "changed"] = "changed"


class DemoService:
    """Coordinates synthetic scans and prepares dashboard-friendly records."""

    def __init__(self, database_path: Path | str) -> None:
        self.repository = Repository(database_path)
        self._scan_lock = asyncio.Lock()

    async def run(self, scenario: str) -> dict[str, object]:
        if scenario not in {"baseline", "changed"}:
            raise ValueError("unsupported simulation scenario")
        if self._scan_lock.locked():
            raise RuntimeError("a demo audit is already running")
        async with self._scan_lock:
            scan = Scan(
                site=f"KALI_DEMO_{scenario.upper()}",
                level=ScanLevel.DISCOVERY,
                profile=ScanProfile.INDUSTRIAL,
                target="simulation://kali-demo",
                simulation=True,
            )
            outcome = await ScanOrchestrator(self.repository).run(
                scan=scan,
                scanner=SimulationScanner(scenario=scenario, delay_seconds=0.12),
                cancellation=CancellationToken(),
            )
            return {
                "scan_id": outcome.scan.id,
                "status": outcome.scan.status.value,
                "scenario": scenario,
                "assets": len(outcome.assets),
                "findings": len(outcome.findings),
            }

    def state(self) -> dict[str, object]:
        self.repository.initialize()
        with self.repository.connect() as connection:
            current_site = connection.execute(
                """SELECT s.id, s.name FROM scans sc JOIN sites s ON s.id=sc.site_id
                ORDER BY sc.rowid DESC LIMIT 1"""
            ).fetchone()
            site_id = int(current_site["id"]) if current_site else -1
            assets = [dict(row) for row in connection.execute(
                """SELECT a.id, a.ip, a.mac, a.hostname, a.vendor, a.device_type,
                    a.criticality, a.confidence, a.risk_score, a.last_seen,
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
            "mode": "simulation",
            "network_traffic": False,
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
        title="Pi-OT Probe Kali Demo",
        description="Local simulation dashboard; it sends no network traffic.",
        version="0.1.0",
    )
    application.state.demo_service = service
    application.mount("/static", StaticFiles(directory=DEMO_DIR / "static"), name="static")

    @application.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(DEMO_DIR / "static" / "index.html")

    @application.get("/api/health")
    async def health() -> dict[str, object]:
        return {"status": "ready", "mode": "simulation", "network_traffic": False}

    @application.get("/api/state")
    async def state() -> dict[str, object]:
        return service.state()

    @application.post("/api/run")
    async def run_demo(request: RunRequest) -> dict[str, object]:
        try:
            return await service.run(request.scenario)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return application


database = Path(os.getenv("PI_OT_DEMO_DATABASE", str(DEFAULT_DATABASE)))
app = create_app(database)
