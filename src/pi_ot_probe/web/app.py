"""Assemble the website; business decisions belong in application/."""
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pi_ot_probe.application.service import ProbeService
from pi_ot_probe.config.paths import STATIC_DIR, default_database
from pi_ot_probe.web.middleware import security_headers
from pi_ot_probe.web.routes import assessment, baselines, inventory, reports, scans
from pi_ot_probe.web.routes import peripherals
from pi_ot_probe.peripherals.manager import NodeManager, load_config
from pi_ot_probe.peripherals.store import EvidenceStore


def create_app(database_path: Path | str | None = None, *, node_configs=None, serial_opener=None) -> FastAPI:
    # One service per app owns scan cancellation and progress; routes share it.
    service = ProbeService(database_path if database_path is not None else default_database())
    manager = NodeManager(load_config() if node_configs is None else node_configs,
                          EvidenceStore(service.repository),
                          **({"opener": serial_opener} if serial_opener else {}))

    @asynccontextmanager
    async def lifespan(app):
        manager.start()
        try:
            yield
        finally:
            manager.stop()

    application = FastAPI(
        title="Pi + ESP Assessment Workstation",
        description="Local network checks, unchanged field instruments, evidence and assessment review.",
        version="0.4.0",
        lifespan=lifespan,
    )
    application.state.probe_service = service
    application.state.node_manager = manager
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @application.get("/console", include_in_schema=False)
    async def console() -> FileResponse:
        return FileResponse(STATIC_DIR / "console.html")

    for route_group in (inventory, scans, baselines, reports, assessment):
        application.include_router(route_group.build_router(service))
    application.middleware("http")(security_headers)
    application.include_router(peripherals.build_router(manager))
    return application


app = create_app()
