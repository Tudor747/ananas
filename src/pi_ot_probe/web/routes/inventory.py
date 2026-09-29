"""HTTP endpoints for inventory; delegate work to ProbeService."""

from fastapi import APIRouter, HTTPException
from pi_ot_probe.application.service import ProbeService
from pi_ot_probe.application.scenarios import VALIDATION_SCENARIOS


def build_router(service: ProbeService) -> APIRouter:
    router = APIRouter()

    @router.get("/api/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ready",
            "mode": "real_discovery",
            "network_traffic_when_scanning": True,
        }

    @router.get("/api/state")
    async def state() -> dict[str, object]:
        return service.state()

    @router.get("/api/networks")
    async def networks() -> dict[str, object]:
        try:
            return await service.networks()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get("/api/validation/scenarios")
    async def validation_scenarios() -> dict[str, object]:
        return {"scenarios": list(VALIDATION_SCENARIOS)}

    return router
