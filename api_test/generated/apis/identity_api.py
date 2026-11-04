"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context, public_request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard, mock, load_tests, identity, oauth, sdk_generation, interoperability, releases, portal
from pydantic import StrictInt, StrictStr
from typing import Any, Optional
from api_test.generated.models.error_response import ErrorResponse
from api_test.generated.models.identity_items import IdentityItems
from api_test.generated.models.identity_result import IdentityResult
from api_test.generated.models.member_change_request import MemberChangeRequest
from api_test.generated.models.session_info import SessionInfo
from api_test.generated.models.workspace_select_request import WorkspaceSelectRequest

router = APIRouter()

@router.get(
    "/auth/login",
    operation_id="login_start",
    tags=["identity",],
    responses={
        303: {"description": "Redirect to provider or application"},400: {"description": "Request rejected", "model": ErrorResponse},401: {"description": "Request rejected", "model": ErrorResponse},403: {"description": "Request rejected", "model": ErrorResponse},409: {"description": "Request rejected", "model": ErrorResponse},429: {"description": "Request rejected", "model": ErrorResponse},503: {"description": "Request rejected", "model": ErrorResponse},
    },
)
async def login_start(context=Depends(public_request_context)) -> Response:
    return await context.call(
        identity.login_start, [],
        upload=False,

    )

@router.get(
    "/auth/callback",
    operation_id="login_callback",
    tags=["identity",],
    responses={
        303: {"description": "Redirect to provider or application"},400: {"description": "Request rejected", "model": ErrorResponse},401: {"description": "Request rejected", "model": ErrorResponse},403: {"description": "Request rejected", "model": ErrorResponse},409: {"description": "Request rejected", "model": ErrorResponse},429: {"description": "Request rejected", "model": ErrorResponse},503: {"description": "Request rejected", "model": ErrorResponse},
    },
)
async def login_callback(context=Depends(public_request_context)) -> Response:
    return await context.call(
        identity.login_callback, [],
        upload=False,

    )

@router.get(
    "/api/session",
    operation_id="session_info",
    tags=["identity",],
    responses={
        200: {"description": "Success", "model": SessionInfo},400: {"description": "Request rejected", "model": ErrorResponse},401: {"description": "Request rejected", "model": ErrorResponse},403: {"description": "Request rejected", "model": ErrorResponse},409: {"description": "Request rejected", "model": ErrorResponse},429: {"description": "Request rejected", "model": ErrorResponse},503: {"description": "Request rejected", "model": ErrorResponse},
    },
)
async def session_info(context=Depends(public_request_context)) -> Response:
    return await context.call(
        identity.session_info, [],
        upload=False,

    )

@router.post(
    "/api/session/logout",
    operation_id="logout",
    tags=["identity",],
    responses={
        200: {"description": "Success", "model": IdentityResult},400: {"description": "Request rejected", "model": ErrorResponse},401: {"description": "Request rejected", "model": ErrorResponse},403: {"description": "Request rejected", "model": ErrorResponse},409: {"description": "Request rejected", "model": ErrorResponse},429: {"description": "Request rejected", "model": ErrorResponse},503: {"description": "Request rejected", "model": ErrorResponse},
    },
)
async def logout(context=Depends(public_request_context)) -> Response:
    return await context.call(
        identity.logout, [],
        upload=False,

    )

@router.post(
    "/api/session/workspace",
    operation_id="select_workspace",
    tags=["identity",],
    responses={
        200: {"description": "Success", "model": SessionInfo},400: {"description": "Request rejected", "model": ErrorResponse},401: {"description": "Request rejected", "model": ErrorResponse},403: {"description": "Request rejected", "model": ErrorResponse},409: {"description": "Request rejected", "model": ErrorResponse},429: {"description": "Request rejected", "model": ErrorResponse},503: {"description": "Request rejected", "model": ErrorResponse},
    },
)
async def select_workspace(context=Depends(public_request_context)) -> Response:
    return await context.call(
        identity.select_workspace, [],
        upload=False,

    )

@router.get(
    "/api/workspace/members",
    operation_id="list_members",
    tags=["identity",],
    responses={
        200: {"description": "Success", "model": IdentityItems},400: {"description": "Request rejected", "model": ErrorResponse},401: {"description": "Request rejected", "model": ErrorResponse},403: {"description": "Request rejected", "model": ErrorResponse},409: {"description": "Request rejected", "model": ErrorResponse},429: {"description": "Request rejected", "model": ErrorResponse},503: {"description": "Request rejected", "model": ErrorResponse},
    },
)
async def list_members(context=Depends(request_context)) -> Response:
    return await context.call(
        identity.list_members, [],
        upload=False,

    )

@router.post(
    "/api/workspace/members",
    operation_id="change_member",
    tags=["identity",],
    responses={
        200: {"description": "Success", "model": IdentityResult},400: {"description": "Request rejected", "model": ErrorResponse},401: {"description": "Request rejected", "model": ErrorResponse},403: {"description": "Request rejected", "model": ErrorResponse},409: {"description": "Request rejected", "model": ErrorResponse},429: {"description": "Request rejected", "model": ErrorResponse},503: {"description": "Request rejected", "model": ErrorResponse},
    },
)
async def change_member(context=Depends(request_context)) -> Response:
    return await context.call(
        identity.change_member, [],
        upload=False,

    )

@router.get(
    "/api/workspace/audit",
    operation_id="audit_events",
    tags=["identity",],
    responses={
        200: {"description": "Success", "model": IdentityItems},400: {"description": "Request rejected", "model": ErrorResponse},401: {"description": "Request rejected", "model": ErrorResponse},403: {"description": "Request rejected", "model": ErrorResponse},409: {"description": "Request rejected", "model": ErrorResponse},429: {"description": "Request rejected", "model": ErrorResponse},503: {"description": "Request rejected", "model": ErrorResponse},
    },
)
async def audit_events(context=Depends(request_context)) -> Response:
    return await context.call(
        identity.audit_events, [],
        upload=False,

    )
