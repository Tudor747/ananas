"""Local control of allowlisted USB nodes and paginated evidence export."""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pi_ot_probe.peripherals.protocol import Command


def build_router(manager):
    router = APIRouter()

    @router.get("/api/nodes")
    def nodes():
        return {"nodes": manager.state()}

    @router.post("/api/nodes/{node}/commands", status_code=202)
    def command(node: str, command: Command, request: Request):
        # USB actions are local-operator actions; reject browser cross-origin calls.
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "cross-origin hardware control is not allowed")
        try:
            return {"id": manager.command(node, command), "status": "queued"}
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/api/peripheral-events")
    def events(after: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=1000)):
        records = manager.store.events(after, limit)
        return {"events": records, "next_after": records[-1]["id"] if records else after}

    @router.get("/api/reports/peripherals.json")
    def json_report(after: int = Query(0, ge=0), limit: int = Query(1000, ge=1, le=1000)):
        return {"schema": "rf-sentinel-evidence-v1", "hardware_verified": False,
                "clock": "host receive UTC; device uptime is unsynchronized",
                **events(after, limit)}

    @router.get("/api/reports/peripherals.md")
    def markdown_report(after: int = Query(0, ge=0), limit: int = Query(1000, ge=1, le=1000)):
        return Response(manager.store.markdown(after, limit), media_type="text/markdown")

    return router
