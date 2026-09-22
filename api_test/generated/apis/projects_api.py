"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard, mock
from pydantic import Field, StrictStr
from typing import Optional
from typing_extensions import Annotated
from api_test.generated.models.delete_response import DeleteResponse
from api_test.generated.models.error_response import ErrorResponse
from api_test.generated.models.project_input import ProjectInput
from api_test.generated.models.project_view import ProjectView
from api_test.generated.models.reference_list import ReferenceList
from api_test.generated.models.revision_list import RevisionList
from api_test.generated.models.save_response import SaveResponse

router = APIRouter()

@router.get("/api/projects/", include_in_schema=False)
@router.get(
    "/api/projects",
    operation_id="list_projects",
    tags=["projects",],
    responses={
        200: {"description": "Success", "model": ReferenceList},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def list_projects(context=Depends(request_context)) -> Response:
    return await context.call(
        documents.list_documents, ['projects'],
        upload=False,

    )

@router.get("/api/projects/{reference:path}/revisions/", include_in_schema=False)
@router.get(
    "/api/projects/{reference:path}/revisions",
    operation_id="list_projects_revisions",
    tags=["projects",],
    responses={
        200: {"description": "Success", "model": RevisionList},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def list_projects_revisions(context=Depends(request_context)) -> Response:
    return await context.call(
        documents.list_revisions, ['projects'],
        upload=False,

    )

@router.get(
    "/api/projects/{reference:path}",
    operation_id="get_projects",
    tags=["projects",],
    responses={
        200: {"description": "Success", "model": ProjectView},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def get_projects(context=Depends(request_context)) -> Response:
    return await context.call(
        documents.get_document, ['projects'],
        upload=False,

    )

@router.put(
    "/api/projects/{reference:path}",
    operation_id="save_projects",
    tags=["projects",],
    responses={
        200: {"description": "Success", "model": SaveResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def save_projects(context=Depends(request_context)) -> Response:
    return await context.call(
        documents.save_document, ['projects'],
        upload=False,

    )

@router.delete(
    "/api/projects/{reference:path}",
    operation_id="delete_projects",
    tags=["projects",],
    responses={
        200: {"description": "Success", "model": DeleteResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def delete_projects(context=Depends(request_context)) -> Response:
    return await context.call(
        documents.delete_document, ['projects'],
        upload=False,

    )

