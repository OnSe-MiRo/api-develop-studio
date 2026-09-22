"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard, mock
from pydantic import StrictStr
from typing import Optional
from api_test.generated.models.error_response import ErrorResponse
from api_test.generated.models.mock_action_response import MockActionResponse
from api_test.generated.models.mock_config_update_request import MockConfigUpdateRequest
from api_test.generated.models.mock_start_request import MockStartRequest
from api_test.generated.models.mock_status_response import MockStatusResponse

router = APIRouter()

@router.get("/api/projects/{reference:path}/mock/", include_in_schema=False)
@router.get(
    "/api/projects/{reference:path}/mock",
    operation_id="get_mock_status",
    tags=["mock",],
    responses={
        200: {"description": "Mock server status", "model": MockStatusResponse},400: {"description": "Invalid request", "model": ErrorResponse},404: {"description": "Project not found", "model": ErrorResponse},
    },
)
async def get_mock_status(context=Depends(request_context)) -> Response:
    return await context.call(
        mock.get_status, [],
        upload=False,

    )

@router.post("/api/projects/{reference:path}/mock/start/", include_in_schema=False)
@router.post(
    "/api/projects/{reference:path}/mock/start",
    operation_id="start_mock_server",
    tags=["mock",],
    responses={
        200: {"description": "Mock server started", "model": MockStatusResponse},400: {"description": "Invalid request or port conflict", "model": ErrorResponse},404: {"description": "Project not found", "model": ErrorResponse},
    },
)
async def start_mock_server(context=Depends(request_context)) -> Response:
    return await context.call(
        mock.start_server, [],
        upload=False,

    )

@router.post("/api/projects/{reference:path}/mock/stop/", include_in_schema=False)
@router.post(
    "/api/projects/{reference:path}/mock/stop",
    operation_id="stop_mock_server",
    tags=["mock",],
    responses={
        200: {"description": "Mock server stopped", "model": MockActionResponse},400: {"description": "Invalid request", "model": ErrorResponse},404: {"description": "Project not found", "model": ErrorResponse},
    },
)
async def stop_mock_server(context=Depends(request_context)) -> Response:
    return await context.call(
        mock.stop_server, [],
        upload=False,

    )

@router.post("/api/projects/{reference:path}/mock/reset/", include_in_schema=False)
@router.post(
    "/api/projects/{reference:path}/mock/reset",
    operation_id="reset_mock_server",
    tags=["mock",],
    responses={
        200: {"description": "Mock server reset", "model": MockActionResponse},400: {"description": "Invalid request", "model": ErrorResponse},404: {"description": "Project not found", "model": ErrorResponse},
    },
)
async def reset_mock_server(context=Depends(request_context)) -> Response:
    return await context.call(
        mock.reset_server, [],
        upload=False,

    )

@router.post("/api/projects/{reference:path}/mock/config/", include_in_schema=False)
@router.post(
    "/api/projects/{reference:path}/mock/config",
    operation_id="update_mock_config",
    tags=["mock",],
    responses={
        200: {"description": "Mock server configuration updated", "model": MockStatusResponse},400: {"description": "Invalid request", "model": ErrorResponse},404: {"description": "Project not found", "model": ErrorResponse},
    },
)
async def update_mock_config(context=Depends(request_context)) -> Response:
    return await context.call(
        mock.update_config, [],
        upload=False,

    )
