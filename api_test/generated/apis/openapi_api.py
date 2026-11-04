"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context, public_request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard, mock, load_tests, identity, oauth, sdk_generation, interoperability, releases, portal
from pydantic import Field, StrictBytes, StrictStr
from typing import Any, Dict, Tuple, Union
from typing_extensions import Annotated
from api_test.generated.models.author_operation_request import AuthorOperationRequest
from api_test.generated.models.author_operation_response import AuthorOperationResponse
from api_test.generated.models.contract_check_request import ContractCheckRequest
from api_test.generated.models.contract_check_response import ContractCheckResponse
from api_test.generated.models.docs_request import DocsRequest
from api_test.generated.models.docs_response import DocsResponse
from api_test.generated.models.error_response import ErrorResponse
from api_test.generated.models.generate_request import GenerateRequest
from api_test.generated.models.open_api_editor_request import OpenApiEditorRequest
from api_test.generated.models.open_api_editor_response import OpenApiEditorResponse

router = APIRouter()

@router.get("/api/projects/{reference:path}/openapi/editor/", include_in_schema=False)
@router.get(
    "/api/projects/{reference:path}/openapi/editor",
    operation_id="get_openapi_editor",
    tags=["openapi",],
    responses={
        200: {"description": "Raw source and current revision", "model": OpenApiEditorResponse},400: {"description": "Saved source is unavailable"},404: {"description": "Project not found"},
    },
)
async def get_openapi_editor(context=Depends(request_context)) -> Response:
    return await context.call(
        openapi.get_openapi_editor, [],
        upload=False,

    )

@router.post("/api/projects/{reference:path}/openapi/editor/", include_in_schema=False)
@router.post(
    "/api/projects/{reference:path}/openapi/editor",
    operation_id="edit_openapi_editor",
    tags=["openapi",],
    responses={
        200: {"description": "Preview or saved source and whole-document diagnostics", "model": OpenApiEditorResponse},400: {"description": "Invalid pointer or contract"},404: {"description": "Project not found"},409: {"description": "Revision or source digest conflict"},
    },
)
async def edit_openapi_editor(context=Depends(request_context)) -> Response:
    return await context.call(
        openapi.edit_openapi_editor, [],
        upload=False,

    )

@router.post("/api/projects/{reference:path}/openapi/operations/", include_in_schema=False)
@router.post(
    "/api/projects/{reference:path}/openapi/operations",
    operation_id="author_operation",
    tags=["openapi",],
    responses={
        200: {"description": "Success", "model": AuthorOperationResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def author_operation(context=Depends(request_context)) -> Response:
    return await context.call(
        openapi.author_operation, [],
        upload=False,

    )

@router.post("/api/projects/{reference:path}/openapi/contract/", include_in_schema=False)
@router.post(
    "/api/projects/{reference:path}/openapi/contract",
    operation_id="check_contract",
    tags=["openapi",],
    responses={
        200: {"description": "Contract analysis", "model": ContractCheckResponse},400: {"description": "Invalid document or request"},404: {"description": "Revision not found"},
    },
)
async def check_contract(context=Depends(request_context)) -> Response:
    return await context.call(
        openapi.check_contract, [],
        upload=False,

    )

@router.post("/api/projects/{reference:path}/openapi/coverage/", include_in_schema=False)
@router.post(
    "/api/projects/{reference:path}/openapi/coverage",
    operation_id="test_coverage",
    tags=["openapi",],
    responses={
        200: {"description": "Coverage or synchronization result"},400: {"description": "Invalid selection"},404: {"description": "Project or case not found"},409: {"description": "Revision conflict"},
    },
)
async def test_coverage(context=Depends(request_context)) -> Response:
    return await context.call(
        openapi.test_coverage, [],
        upload=False,

    )

@router.post("/api/docs/", include_in_schema=False)
@router.post(
    "/api/docs",
    operation_id="inspect_document",
    tags=["openapi",],
    responses={
        200: {"description": "Success", "model": DocsResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def inspect_document(context=Depends(request_context)) -> Response:
    return await context.call(
        openapi.inspect_document, [],
        upload=False,

    )

@router.post("/api/generate/", include_in_schema=False)
@router.post(
    "/api/generate",
    operation_id="generate_client",
    tags=["openapi",],
    responses={
        200: {"description": "ZIP archive", "model": bytes},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},504: {"description": "Execution timeout", "model": ErrorResponse},
    },
)
async def generate_client(context=Depends(request_context)) -> Response:
    return await context.call(
        openapi.generate_client, [],
        upload=False,

    )
