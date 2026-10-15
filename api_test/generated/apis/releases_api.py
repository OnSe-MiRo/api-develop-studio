"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context, public_request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard, mock, load_tests, identity, oauth, sdk_generation, interoperability, releases, portal
from pydantic import Field, StrictStr
from typing import Optional
from typing_extensions import Annotated
from api_test.generated.models.api_release import ApiRelease
from api_test.generated.models.api_release_list import ApiReleaseList
from api_test.generated.models.api_release_source import ApiReleaseSource
from api_test.generated.models.error_response import ErrorResponse
from api_test.generated.models.release_create_request import ReleaseCreateRequest
from api_test.generated.models.release_transition_request import ReleaseTransitionRequest

router = APIRouter()

@router.get(
    "/api/projects/{reference:path}/releases",
    operation_id="list_releases",
    tags=["releases",],
    responses={
        200: {"description": "Success", "model": ApiReleaseList},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Role denied", "model": ErrorResponse},404: {"description": "Not found", "model": ErrorResponse},409: {"description": "Revision or state conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def list_releases(context=Depends(request_context)) -> Response:
    return await context.call(
        releases.list_releases, [],
        upload=False,

    )

@router.post(
    "/api/projects/{reference:path}/releases",
    operation_id="create_release",
    tags=["releases",],
    responses={
        201: {"description": "Success", "model": ApiRelease},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Role denied", "model": ErrorResponse},404: {"description": "Not found", "model": ErrorResponse},409: {"description": "Revision or state conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def create_release(context=Depends(request_context)) -> Response:
    return await context.call(
        releases.create_release, [],
        upload=False,

    )

@router.get(
    "/api/projects/{reference:path}/releases/{releaseId}",
    operation_id="get_release",
    tags=["releases",],
    responses={
        200: {"description": "Success", "model": ApiRelease},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Role denied", "model": ErrorResponse},404: {"description": "Not found", "model": ErrorResponse},409: {"description": "Revision or state conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def get_release(context=Depends(request_context)) -> Response:
    return await context.call(
        releases.get_release, [],
        upload=False,

    )

@router.get(
    "/api/projects/{reference:path}/releases/{releaseId}/source",
    operation_id="get_release_source",
    tags=["releases",],
    responses={
        200: {"description": "Success", "model": ApiReleaseSource},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Role denied", "model": ErrorResponse},404: {"description": "Not found", "model": ErrorResponse},409: {"description": "Revision or state conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def get_release_source(context=Depends(request_context)) -> Response:
    return await context.call(
        releases.get_release_source, [],
        upload=False,

    )

@router.post(
    "/api/projects/{reference:path}/releases/{releaseId}/transition",
    operation_id="transition_release",
    tags=["releases",],
    responses={
        200: {"description": "Success", "model": ApiRelease},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Role denied", "model": ErrorResponse},404: {"description": "Not found", "model": ErrorResponse},409: {"description": "Revision or state conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def transition_release(context=Depends(request_context)) -> Response:
    return await context.call(
        releases.transition_release, [],
        upload=False,

    )
