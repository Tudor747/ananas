from fastapi import APIRouter, Query

from pi_ot_probe.database.repository import Repository


def build_router(repository: Repository) -> APIRouter:
    router = APIRouter(prefix="/api/findings", tags=["findings"])

    @router.get("")
    def list_findings(limit: int = Query(100, ge=1, le=500)) -> list[dict[str, object]]:
        return repository.list_findings(limit)

    return router

