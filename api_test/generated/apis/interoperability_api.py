"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context, public_request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard, mock, load_tests, identity, oauth, sdk_generation, interoperability, releases, portal
from api_test.generated.models.curl_export_request import CurlExportRequest
from api_test.generated.models.curl_export_response import CurlExportResponse
from api_test.generated.models.error_response import ErrorResponse
from api_test.generated.models.import_preview import ImportPreview
from api_test.generated.models.import_request import ImportRequest
from api_test.generated.models.import_result import ImportResult

router = APIRouter()

@router.post(
    "/api/interoperability/preview",
    operation_id="interoperability_preview",
    tags=["interoperability",],
    responses={
        200: {"description": "Success", "model": ImportPreview},400: {"description": "Invalid request", "model": ErrorResponse},404: {"description": "Missing document", "model": ErrorResponse},409: {"description": "Preview or revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def interoperability_preview(context=Depends(request_context)) -> Response:
    return await context.call(
        interoperability.preview, [],
        upload=False,

    )

@router.post(
    "/api/interoperability/apply",
    operation_id="interoperability_apply",
    tags=["interoperability",],
    responses={
        200: {"description": "Success", "model": ImportResult},400: {"description": "Invalid request", "model": ErrorResponse},404: {"description": "Missing document", "model": ErrorResponse},409: {"description": "Preview or revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def interoperability_apply(context=Depends(request_context)) -> Response:
    return await context.call(
        interoperability.apply_import, [],
        upload=False,

    )

@router.post(
    "/api/interoperability/curl",
    operation_id="interoperability_curl",
    tags=["interoperability",],
    responses={
        200: {"description": "Success", "model": CurlExportResponse},400: {"description": "Invalid request", "model": ErrorResponse},404: {"description": "Missing document", "model": ErrorResponse},409: {"description": "Preview or revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def interoperability_curl(context=Depends(request_context)) -> Response:
    return await context.call(
        interoperability.export, [],
        upload=False,

    )
