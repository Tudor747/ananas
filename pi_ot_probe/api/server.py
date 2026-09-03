"""FastAPI application factory with mandatory bearer authentication."""

from __future__ import annotations

from secrets import compare_digest

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from pi_ot_probe.api.routes.assets import build_router as assets_router
from pi_ot_probe.api.routes.scans import build_router as scans_router
from pi_ot_probe.api.routes.system import build_router as system_router
from pi_ot_probe.database.repository import Repository


def create_app(repository: Repository, api_token: str) -> FastAPI:
    if len(api_token) < 32:
        raise ValueError("API token must be at least 32 characters; no default credential is provided")
    bearer = HTTPBearer(auto_error=False)

    def authenticate(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> None:
        if credentials is None or not compare_digest(credentials.credentials, api_token):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API token")

    app = FastAPI(title="Pi-OT Security Probe", version="0.4.0", dependencies=[Depends(authenticate)])
    app.include_router(system_router(repository))
    app.include_router(assets_router(repository))
    app.include_router(scans_router(repository))
    return app
