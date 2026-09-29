"""Assemble the website; business decisions belong in application/."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pi_ot_probe.application.service import ProbeService
from pi_ot_probe.config.paths import STATIC_DIR, default_database
from pi_ot_probe.web.middleware import security_headers
from pi_ot_probe.web.routes import baselines, inventory, reports, scans


def create_app(database_path: Path | str | None = None) -> FastAPI:
    # One service per app owns scan cancellation and progress; routes share it.
    service = ProbeService(database_path if database_path is not None else default_database())
    application = FastAPI(
        title="Pi-OT Probe Engineering Console",
        description="Local discovery, verification, baseline, and raw evidence dashboard.",
        version="0.4.0",
    )
    application.state.probe_service = service
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    for route_group in (inventory, scans, baselines, reports):
        application.include_router(route_group.build_router(service))
    application.middleware("http")(security_headers)
    return application


app = create_app()
