"""Instrument records and assessment review; these endpoints send no scan traffic."""

from fastapi import APIRouter, HTTPException

from pi_ot_probe.application.service import ProbeService
from pi_ot_probe.web.schemas import AssessmentReviewRequest, FieldObservationRequest, InstrumentRequest


def build_router(service: ProbeService) -> APIRouter:
    router = APIRouter()

    @router.get("/api/assessment")
    async def assessment() -> dict:
        return service.assessment()

    @router.get("/api/instruments")
    async def instruments() -> dict:
        return {"instruments": service.instruments.instruments()}

    @router.post("/api/instruments", status_code=201)
    async def register(request: InstrumentRequest) -> dict:
        try:
            return service.instruments.register(**request.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/field-observations", status_code=201)
    async def observation(request: FieldObservationRequest) -> dict:
        try:
            service.require_current_site(request.site)
            return service.instruments.record(**request.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/assessment/{finding_id}/review")
    async def review(finding_id: str, request: AssessmentReviewRequest) -> dict:
        try:
            state = service.require_current_site(request.site)
            service.instruments.review(state, finding_id, request.status, request.note)
            return {"saved": True}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
