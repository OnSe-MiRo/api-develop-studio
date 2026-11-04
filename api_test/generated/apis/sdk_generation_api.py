"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context, public_request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard, mock, load_tests, identity, oauth, sdk_generation, interoperability, releases, portal
from pydantic import StrictBytes, StrictStr
from typing import Tuple, Union
from api_test.generated.models.error_response import ErrorResponse
from api_test.generated.models.run_job import RunJob
from api_test.generated.models.sdk_generation_request import SdkGenerationRequest

router = APIRouter()

@router.post(
    "/api/generations",
    operation_id="submit_sdk_generation",
    tags=["sdk_generation",],
    responses={
        202: {"description": "Accepted. Poll the returned runId through GET /api/runs/{runId}; acceptance is not generation success.", "model": RunJob},400: {"description": "Invalid generation request or source", "model": ErrorResponse},404: {"description": "Job, project or retained artifact not found", "model": ErrorResponse},409: {"description": "Project revision conflict or SDK artifact not ready", "model": ErrorResponse},413: {"description": "Request body too large", "model": ErrorResponse},429: {"description": "Shared queue or download limit exceeded", "model": ErrorResponse},503: {"description": "Worker or storage unavailable", "model": ErrorResponse},
    },
)
async def submit_sdk_generation(context=Depends(request_context)) -> Response:
    return await context.call(
        sdk_generation.submit_generation, [],
        upload=False,

    )

@router.get(
    "/api/generations/{runId}/artifact",
    operation_id="download_sdk_artifact",
    tags=["sdk_generation",],
    responses={
        200: {"description": "Bounded generated SDK ZIP. Temporary source and Java output directories have already been removed.", "model": bytes},404: {"description": "Job, project or retained artifact not found", "model": ErrorResponse},409: {"description": "Project revision conflict or SDK artifact not ready", "model": ErrorResponse},429: {"description": "Shared queue or download limit exceeded", "model": ErrorResponse},503: {"description": "Worker or storage unavailable", "model": ErrorResponse},
    },
)
async def download_sdk_artifact(context=Depends(request_context)) -> Response:
    return await context.call(
        sdk_generation.download_artifact, [],
        upload=False,

    )
