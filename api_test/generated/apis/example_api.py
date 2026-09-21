"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard, mock
from pydantic import Field, StrictStr
from typing_extensions import Annotated
from api_test.generated.models.error_response import ErrorResponse
from api_test.generated.models.example_input import ExampleInput
from api_test.generated.models.example_response import ExampleResponse

router = APIRouter()

@router.get("/example-api/", include_in_schema=False)
@router.get(
    "/example-api",
    operation_id="get_example",
    tags=["example",],
    responses={
        200: {"description": "Success", "model": ExampleResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},201: {"description": "Example user created", "model": ExampleResponse},401: {"description": "Missing or invalid example API key", "model": ExampleResponse},404: {"description": "Example endpoint not found", "model": ExampleResponse},
    },
)
async def get_example(context=Depends(request_context)) -> Response:
    return await context.call(
        example.handle_example, [],
        upload=False,

    )

@router.post("/example-api/", include_in_schema=False)
@router.post(
    "/example-api",
    operation_id="post_example",
    tags=["example",],
    responses={
        200: {"description": "Success", "model": ExampleResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},201: {"description": "Example user created", "model": ExampleResponse},401: {"description": "Missing or invalid example API key", "model": ExampleResponse},404: {"description": "Example endpoint not found", "model": ExampleResponse},
    },
)
async def post_example(context=Depends(request_context)) -> Response:
    return await context.call(
        example.handle_example, [],
        upload=False,

    )

@router.get(
    "/example-api/{reference:path}",
    operation_id="get_example_resource",
    tags=["example",],
    responses={
        200: {"description": "Success", "model": ExampleResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},201: {"description": "Example user created", "model": ExampleResponse},401: {"description": "Missing or invalid example API key", "model": ExampleResponse},404: {"description": "Example endpoint not found", "model": ExampleResponse},
    },
)
async def get_example_resource(context=Depends(request_context)) -> Response:
    return await context.call(
        example.handle_example, [],
        upload=False,

    )

@router.post(
    "/example-api/{reference:path}",
    operation_id="post_example_resource",
    tags=["example",],
    responses={
        200: {"description": "Success", "model": ExampleResponse},400: {"description": "Invalid request", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Revision conflict", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},201: {"description": "Example user created", "model": ExampleResponse},401: {"description": "Missing or invalid example API key", "model": ExampleResponse},404: {"description": "Example endpoint not found", "model": ExampleResponse},
    },
)
async def post_example_resource(context=Depends(request_context)) -> Response:
    return await context.call(
        example.handle_example, [],
        upload=False,

    )

