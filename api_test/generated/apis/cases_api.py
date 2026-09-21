"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard, mock
from pydantic import Field, StrictStr
from typing import Optional
from typing_extensions import Annotated
from api_test.generated.models.case_input import CaseInput
from api_test.generated.models.case_view import CaseView
from api_test.generated.models.delete_response import DeleteResponse
from api_test.generated.models.error_response import ErrorResponse
from api_test.generated.models.reference_list import ReferenceList
from api_test.generated.models.revision_list import RevisionList
from api_test.generated.models.save_response import SaveResponse

router = APIRouter()

@router.get("/api/cases/", include_in_schema=False)
@router.get(
    "/api/cases",
    operation_id="list_cases",
    tags=["cases",],
    responses={
        200: {"description": "Success", "model": ReferenceList},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def list_cases(context=Depends(request_context)) -> Response:
    return await context.call(
        documents.list_documents, ['cases'],
        upload=False,

    )

@router.get("/api/cases/{reference:path}/revisions/", include_in_schema=False)
@router.get(
    "/api/cases/{reference:path}/revisions",
    operation_id="list_cases_revisions",
    tags=["cases",],
    responses={
        200: {"description": "Success", "model": RevisionList},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def list_cases_revisions(context=Depends(request_context)) -> Response:
    return await context.call(
        documents.list_revisions, ['cases'],
        upload=False,

    )

@router.get(
    "/api/cases/{reference:path}",
    operation_id="get_cases",
    tags=["cases",],
    responses={
        200: {"description": "Success", "model": CaseView},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def get_cases(context=Depends(request_context)) -> Response:
    return await context.call(
        documents.get_document, ['cases'],
        upload=False,

    )

@router.put(
    "/api/cases/{reference:path}",
    operation_id="save_cases",
    tags=["cases",],
    responses={
        200: {"description": "Success", "model": SaveResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def save_cases(context=Depends(request_context)) -> Response:
    return await context.call(
        documents.save_document, ['cases'],
        upload=False,

    )

@router.delete(
    "/api/cases/{reference:path}",
    operation_id="delete_cases",
    tags=["cases",],
    responses={
        200: {"description": "Success", "model": DeleteResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def delete_cases(context=Depends(request_context)) -> Response:
    return await context.call(
        documents.delete_document, ['cases'],
        upload=False,

    )

