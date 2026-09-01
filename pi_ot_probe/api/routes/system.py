from fastapi import APIRouter

from pi_ot_probe.database.repository import Repository


def build_router(repository: Repository) -> APIRouter:
    router = APIRouter(prefix="/api/system", tags=["system"])

    @router.get("/status")
    def status() -> dict[str, object]:
        return {"status": "ready", "database_counts": repository.counts()}

    return router
