"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard, mock
from pydantic import StrictStr
from typing import Optional
from api_test.generated.models.error_response import ErrorResponse
from api_test.generated.models.ownership_request import OwnershipRequest
from api_test.generated.models.ownership_response import OwnershipResponse

router = APIRouter()

@router.get("/api/ownership/", include_in_schema=False)
@router.get(
    "/api/ownership",
    operation_id="get_ownership",
    tags=["ownership",],
    responses={
        200: {"description": "Success", "model": OwnershipResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def get_ownership(context=Depends(request_context)) -> Response:
    return await context.call(
        ownership.get_ownership, [],
        upload=False,

    )

@router.post("/api/ownership/", include_in_schema=False)
@router.post(
    "/api/ownership",
    operation_id="ownership_action",
    tags=["ownership",],
    responses={
        200: {"description": "Success", "model": OwnershipResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def ownership_action(context=Depends(request_context)) -> Response:
    return await context.call(
        ownership.perform_action, [],
        upload=False,

    )

@router.post(
    "/api/ownership/{action:path}",
    operation_id="perform_ownership_action",
    tags=["ownership",],
    responses={
        200: {"description": "Success", "model": OwnershipResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def perform_ownership_action(context=Depends(request_context)) -> Response:
    return await context.call(
        ownership.perform_action, [],
        upload=False,

    )

