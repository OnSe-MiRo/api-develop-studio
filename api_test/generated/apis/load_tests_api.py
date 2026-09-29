"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard, mock, load_tests
from datetime import datetime
from pydantic import Field, StrictStr
from typing import Any, Dict, Optional
from typing_extensions import Annotated

router = APIRouter()

@router.get(
    "/api/load-tests/runs",
    operation_id="list_load_test_runs",
    tags=["load-tests",],
    responses={
        200: {"description": "Page of runs", "model": object},400: {"description": "Invalid filter or cursor"},413: {"description": "Serialized response exceeds 1 MiB"},
    },
)
async def list_load_test_runs(context=Depends(request_context)) -> Response:
    return await context.call(
        load_tests.list_load_test_runs, [],
        upload=False,

    )

@router.post(
    "/api/load-tests/runs",
    operation_id="create_load_test_run",
    tags=["load-tests",],
    responses={
        201: {"description": "Created", "model": object},400: {"description": "Invalid bundle"},409: {"description": "Duplicate run ID"},413: {"description": "Bundle too large"},
    },
)
async def create_load_test_run(context=Depends(request_context)) -> Response:
    return await context.call(
        load_tests.create_load_test_run, [],
        upload=False,

    )

@router.get(
    "/api/load-tests/runs/{runId}",
    operation_id="get_load_test_run",
    tags=["load-tests",],
    responses={
        200: {"description": "Run details", "model": object},404: {"description": "Run not found"},413: {"description": "Serialized response exceeds 1 MiB"},
    },
)
async def get_load_test_run(context=Depends(request_context)) -> Response:
    return await context.call(
        load_tests.get_load_test_run, [],
        upload=False,

    )

@router.get(
    "/api/load-tests/runs/{runId}/series",
    operation_id="get_load_test_series",
    tags=["load-tests",],
    responses={
        200: {"description": "Time series", "model": object},400: {"description": "Invalid query"},404: {"description": "Run not found"},413: {"description": "Serialized response exceeds 1 MiB"},
    },
)
async def get_load_test_series(context=Depends(request_context)) -> Response:
    return await context.call(
        load_tests.get_load_test_series, [],
        upload=False,

    )

@router.get(
    "/api/load-tests/compare",
    operation_id="compare_load_test_runs",
    tags=["load-tests",],
    responses={
        200: {"description": "Comparison", "model": object},400: {"description": "Incompatible runs"},404: {"description": "Run not found"},413: {"description": "Serialized response exceeds 1 MiB"},
    },
)
async def compare_load_test_runs(context=Depends(request_context)) -> Response:
    return await context.call(
        load_tests.compare_load_test_runs, [],
        upload=False,

    )
