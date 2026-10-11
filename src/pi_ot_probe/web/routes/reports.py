"""HTTP endpoints for reports; delegate work to ProbeService."""

from fastapi import APIRouter, HTTPException
from pi_ot_probe.application.service import ProbeService
from fastapi.responses import JSONResponse, Response
from pi_ot_probe.reports.site import assets_csv, site_report
from pi_ot_probe.reports.assessment import assessment_markdown, assessment_report


def build_router(service: ProbeService) -> APIRouter:
    router = APIRouter()

    @router.get("/api/reports/assessment.json")
    async def assessment_json() -> JSONResponse:
        return JSONResponse(assessment_report(service.assessment()), headers={
            "Content-Disposition": 'attachment; filename="network-assessment.json"'
        })

    @router.get("/api/reports/assessment.md")
    async def assessment_text() -> Response:
        return Response(assessment_markdown(service.assessment()), media_type="text/markdown; charset=utf-8", headers={
            "Content-Disposition": 'attachment; filename="network-assessment.md"'
        })

    @router.get("/api/reports/site.json")
    async def json_report() -> JSONResponse:
        return JSONResponse(site_report(service.state()), headers={
            "Content-Disposition": 'attachment; filename="pi-ot-site-report.json"'
        })

    @router.get("/api/reports/assets.csv")
    async def csv_report() -> Response:
        return Response(
            assets_csv(service.state()),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="pi-ot-assets.csv"'},
        )

    return router
