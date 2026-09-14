"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard
from pydantic import Field, StrictBytes, StrictStr
from typing import Tuple, Union
from typing_extensions import Annotated
from api_test.generated.models.error_response import ErrorResponse
from api_test.generated.models.upload_response import UploadResponse

router = APIRouter()

@router.post(
    "/api/uploads/{reference:path}",
    operation_id="upload_attachment",
    tags=["uploads",],
    responses={
        200: {"description": "Success", "model": UploadResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},
    },
)
async def upload_attachment(context=Depends(request_context)) -> Response:
    return await context.call(
        uploads.upload_attachment, [],
        upload=True,

    )

