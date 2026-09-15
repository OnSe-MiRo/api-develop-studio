"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard
from pydantic import StrictStr
from typing import Any
from api_test.generated.models.error_response import ErrorResponse
from api_test.generated.models.quick_request import QuickRequest
from api_test.generated.models.quick_response import QuickResponse
from api_test.generated.models.run_job import RunJob
from api_test.generated.models.run_request import RunRequest
from api_test.generated.models.run_response import RunResponse

router = APIRouter()

@router.post("/api/request/", include_in_schema=False)
@router.post(
    "/api/request",
    operation_id="send_request",
    tags=["execution",],
    responses={
        200: {"description": "Success", "model": QuickResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},502: {"description": "Upstream connection failure", "model": ErrorResponse},504: {"description": "Upstream timeout", "model": ErrorResponse},
    },
)
async def send_request(context=Depends(request_context)) -> Response:
    return await context.call(
        execution.send_request, [],
        upload=False,

    )

@router.post("/api/run/", include_in_schema=False)
@router.post(
    "/api/run",
    operation_id="run_tests",
    tags=["execution",],
    responses={
        200: {"description": "Success", "model": RunResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},429: {"description": "Concurrent execution limit exceeded"},504: {"description": "Execution timeout", "model": ErrorResponse},
    },
)
async def run_tests(context=Depends(request_context)) -> Response:
    return await context.call(
        execution.run_tests, [],
        upload=False,

    )

@router.post(
    "/api/runs",
    operation_id="submit_run",
    tags=["execution",],
    responses={
        202: {"description": "Job status", "model": RunJob},413: {"description": "Execution request exceeds 1 MiB"},400: {"description": "Request rejected", "model": ErrorResponse},403: {"description": "Request rejected", "model": ErrorResponse},404: {"description": "Request rejected", "model": ErrorResponse},429: {"description": "Request rejected", "model": ErrorResponse},503: {"description": "Request rejected", "model": ErrorResponse},
    },
)
async def submit_run(context=Depends(request_context)) -> Response:
    return await context.call(
        execution.submit_run, [],
        upload=False,

    )

@router.get(
    "/api/runs/{runId}",
    operation_id="get_run",
    tags=["execution",],
    responses={
        200: {"description": "Job status", "model": RunJob},400: {"description": "Request rejected", "model": ErrorResponse},403: {"description": "Request rejected", "model": ErrorResponse},404: {"description": "Request rejected", "model": ErrorResponse},429: {"description": "Request rejected", "model": ErrorResponse},503: {"description": "Request rejected", "model": ErrorResponse},
    },
)
async def get_run(context=Depends(request_context)) -> Response:
    return await context.call(
        execution.get_run, [context.request.path_params["runId"]],
        upload=False,

    )

@router.post(
    "/api/runs/{runId}/cancel",
    operation_id="cancel_run",
    tags=["execution",],
    responses={
        200: {"description": "Job status", "model": RunJob},400: {"description": "Request rejected", "model": ErrorResponse},403: {"description": "Request rejected", "model": ErrorResponse},404: {"description": "Request rejected", "model": ErrorResponse},429: {"description": "Request rejected", "model": ErrorResponse},503: {"description": "Request rejected", "model": ErrorResponse},
    },
)
async def cancel_run(context=Depends(request_context)) -> Response:
    return await context.call(
        execution.cancel_run, [context.request.path_params["runId"]],
        upload=False,

    )

