"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context, public_request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard, mock, load_tests, identity, oauth, sdk_generation, interoperability, releases, portal
from pydantic import Field, StrictBytes, StrictStr
from typing import Optional, Tuple, Union
from typing_extensions import Annotated
from api_test.generated.models.api_release_list import ApiReleaseList
from api_test.generated.models.error_response import ErrorResponse
from api_test.generated.models.release_portal import ReleasePortal
from api_test.generated.models.release_sdk_purge_request import ReleaseSdkPurgeRequest
from api_test.generated.models.release_sdk_purge_result import ReleaseSdkPurgeResult
from api_test.generated.models.release_sdk_request import ReleaseSdkRequest
from api_test.generated.models.run_job import RunJob

router = APIRouter()

@router.get(
    "/api/projects/{reference:path}/portal",
    operation_id="list_portal_releases",
    tags=["portal",],
    responses={
        200: {"description": "Success", "model": ApiReleaseList},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Role denied", "model": ErrorResponse},404: {"description": "Not found", "model": ErrorResponse},409: {"description": "Release or artifact conflict", "model": ErrorResponse},429: {"description": "Capacity exceeded", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def list_portal_releases(context=Depends(request_context)) -> Response:
    return await context.call(
        portal.list_portal_releases, [],
        upload=False,

    )

@router.get(
    "/api/projects/{reference:path}/portal/{releaseId}",
    operation_id="get_portal",
    tags=["portal",],
    responses={
        200: {"description": "Success", "model": ReleasePortal},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Role denied", "model": ErrorResponse},404: {"description": "Not found", "model": ErrorResponse},409: {"description": "Release or artifact conflict", "model": ErrorResponse},429: {"description": "Capacity exceeded", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def get_portal(context=Depends(request_context)) -> Response:
    return await context.call(
        portal.get_portal, [],
        upload=False,

    )

@router.post(
    "/api/projects/{reference:path}/portal/{releaseId}/sdk",
    operation_id="submit_release_sdk",
    tags=["portal",],
    responses={
        202: {"description": "Success", "model": RunJob},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Role denied", "model": ErrorResponse},404: {"description": "Not found", "model": ErrorResponse},409: {"description": "Release or artifact conflict", "model": ErrorResponse},429: {"description": "Capacity exceeded", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def submit_release_sdk(context=Depends(request_context)) -> Response:
    return await context.call(
        portal.submit_release_sdk, [],
        upload=False,

    )

@router.get(
    "/api/projects/{reference:path}/portal/{releaseId}/sdk/{language}",
    operation_id="download_release_sdk",
    tags=["portal",],
    responses={
        200: {"description": "Success", "model": bytes},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Role denied", "model": ErrorResponse},404: {"description": "Not found", "model": ErrorResponse},409: {"description": "Release or artifact conflict", "model": ErrorResponse},429: {"description": "Capacity exceeded", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def download_release_sdk(context=Depends(request_context)) -> Response:
    return await context.call(
        portal.download_release_sdk, [],
        upload=False,

    )

@router.post(
    "/api/projects/{reference:path}/portal/{releaseId}/sdk/{language}/purge",
    operation_id="purge_release_sdk",
    tags=["portal",],
    responses={
        200: {"description": "Success", "model": ReleaseSdkPurgeResult},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Role denied", "model": ErrorResponse},404: {"description": "Not found", "model": ErrorResponse},409: {"description": "Release or artifact conflict", "model": ErrorResponse},429: {"description": "Capacity exceeded", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def purge_release_sdk(context=Depends(request_context)) -> Response:
    return await context.call(
        portal.purge_release_sdk, [],
        upload=False,

    )
