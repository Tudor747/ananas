"""HTTP endpoints for scans; delegate work to ProbeService."""

from fastapi import APIRouter, HTTPException
from pi_ot_probe.application.service import ProbeService
from pi_ot_probe.web.schemas import DiscoveryRequest, ServiceVerificationRequest, WebsiteInspectionRequest, WifiInventoryRequest


def build_router(service: ProbeService) -> APIRouter:
    router = APIRouter()

    @router.post("/api/real/run")
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

    @router.post("/api/real/verify")
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

    @router.post("/api/wifi/refresh")
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

    @router.post("/api/real/web")
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

    @router.post("/api/cancel")
    async def cancel() -> dict[str, object]:
        return {"cancel_requested": service.cancel()}

    return router
