from fastapi import APIRouter, Query

from pi_ot_probe.database.repository import Repository


def build_router(repository: Repository) -> APIRouter:
    router = APIRouter(prefix="/api/assets", tags=["assets"])

    @router.get("")
    def list_assets(site: str = Query(min_length=1, max_length=100)) -> list[dict[str, object]]:
        return repository.list_assets(site)

    return router

