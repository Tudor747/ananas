"""HTTP endpoints for baselines; delegate work to ProbeService."""

from fastapi import APIRouter, HTTPException
from pi_ot_probe.application.service import ProbeService
from pi_ot_probe.web.schemas import BaselineRequest, ChangeReviewRequest


def build_router(service: ProbeService) -> APIRouter:
    router = APIRouter()

    @router.post("/api/baseline")
    async def create_baseline(request: BaselineRequest) -> dict[str, object]:
        try:
            return service.create_baseline(request.name)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/api/changes/{change_id}/acknowledge")
    async def acknowledge_change(change_id: int) -> dict[str, object]:
        acknowledged = service.acknowledge_change(change_id)
        if not acknowledged:
            raise HTTPException(status_code=404, detail="change was not found")
        return {"acknowledged": True, "change_id": change_id}

    @router.post("/api/changes/{change_id}/triage")
    async def triage_change(change_id: int, request: ChangeReviewRequest) -> dict[str, object]:
        try:
            updated = service.triage_change(change_id, request.status, request.note)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not updated:
            raise HTTPException(status_code=404, detail="change was not found")
        return {"updated": True, "change_id": change_id, "status": request.status}

    return router
