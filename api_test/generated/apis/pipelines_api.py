"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard
from pydantic import Field, StrictStr
from typing import Optional
from typing_extensions import Annotated
from api_test.generated.models.delete_response import DeleteResponse
from api_test.generated.models.error_response import ErrorResponse
from api_test.generated.models.pipeline_document import PipelineDocument
from api_test.generated.models.reference_list import ReferenceList
from api_test.generated.models.revision_list import RevisionList
from api_test.generated.models.save_response import SaveResponse

router = APIRouter()

@router.get("/api/pipelines/", include_in_schema=False)
@router.get(
    "/api/pipelines",
    operation_id="list_pipelines",
    tags=["pipelines",],
    responses={
        200: {"description": "Success", "model": ReferenceList},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def list_pipelines(context=Depends(request_context)) -> Response:
    return await context.call(
        documents.list_documents, ['pipelines'],
        upload=False,

    )

@router.get("/api/pipelines/{reference:path}/revisions/", include_in_schema=False)
@router.get(
    "/api/pipelines/{reference:path}/revisions",
    operation_id="list_pipelines_revisions",
    tags=["pipelines",],
    responses={
        200: {"description": "Success", "model": RevisionList},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def list_pipelines_revisions(context=Depends(request_context)) -> Response:
    return await context.call(
        documents.list_revisions, ['pipelines'],
        upload=False,

    )

@router.get(
    "/api/pipelines/{reference:path}",
    operation_id="get_pipelines",
    tags=["pipelines",],
    responses={
        200: {"description": "Success", "model": PipelineDocument},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def get_pipelines(context=Depends(request_context)) -> Response:
    return await context.call(
        documents.get_document, ['pipelines'],
        upload=False,

    )

@router.put(
    "/api/pipelines/{reference:path}",
    operation_id="save_pipelines",
    tags=["pipelines",],
    responses={
        200: {"description": "Success", "model": SaveResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def save_pipelines(context=Depends(request_context)) -> Response:
    return await context.call(
        documents.save_document, ['pipelines'],
        upload=False,

    )

@router.delete(
    "/api/pipelines/{reference:path}",
    operation_id="delete_pipelines",
    tags=["pipelines",],
    responses={
        200: {"description": "Success", "model": DeleteResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def delete_pipelines(context=Depends(request_context)) -> Response:
    return await context.call(
        documents.delete_document, ['pipelines'],
        upload=False,

    )

