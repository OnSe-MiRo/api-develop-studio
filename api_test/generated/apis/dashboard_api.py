"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard, mock, load_tests
from pydantic import Field, StrictStr
from typing import Any, Optional
from typing_extensions import Annotated
from api_test.generated.models.dashboard_response import DashboardResponse
from api_test.generated.models.error_response import ErrorResponse
from api_test.generated.models.execution_detail import ExecutionDetail
from api_test.generated.models.run_job import RunJob

router = APIRouter()

@router.get(
    "/api/executions/{runId}",
    operation_id="get_execution",
    tags=["dashboard",],
    responses={
        200: {"description": "Success", "model": ExecutionDetail},400: {"description": "Request rejected"},403: {"description": "Request rejected"},404: {"description": "Request rejected"},409: {"description": "Request rejected"},429: {"description": "Request rejected"},503: {"description": "Request rejected"},
    },
)
async def get_execution(context=Depends(request_context)) -> Response:
    return await context.call(
        dashboard.get_execution, [context.request.path_params["runId"]],
        upload=False,

    )

@router.post(
    "/api/executions/{runId}/rerun",
    operation_id="rerun_execution",
    tags=["dashboard",],
    responses={
        202: {"description": "Success", "model": RunJob},413: {"description": "Request exceeds 1 MiB"},400: {"description": "Request rejected"},403: {"description": "Request rejected"},404: {"description": "Request rejected"},409: {"description": "Request rejected"},429: {"description": "Request rejected"},503: {"description": "Request rejected"},
    },
)
async def rerun_execution(context=Depends(request_context)) -> Response:
    return await context.call(
        dashboard.rerun_execution, [context.request.path_params["runId"]],
        upload=False,

    )

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

