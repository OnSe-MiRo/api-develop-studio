"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard
from pydantic import StrictStr
from typing import Optional
from api_test.generated.models.dashboard_response import DashboardResponse
from api_test.generated.models.error_response import ErrorResponse

router = APIRouter()

@router.get("/api/dashboard/", include_in_schema=False)
@router.get(
    "/api/dashboard",
    operation_id="get_dashboard",
    tags=["dashboard",],
    responses={
        200: {"description": "Success", "model": DashboardResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def get_dashboard(context=Depends(request_context)) -> Response:
    return await context.call(
        dashboard.get_dashboard, [],
        upload=False,

    )

