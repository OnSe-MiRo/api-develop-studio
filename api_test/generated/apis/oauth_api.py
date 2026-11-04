"""Generated from openapi/studio.yaml. Regenerate with scripts/generate_server.py."""
from fastapi import APIRouter, Depends, Response
from api_test.dependencies import request_context, public_request_context
from api_test.implementations import documents, execution, openapi, ownership, uploads, example, dashboard, mock, load_tests, identity, oauth, sdk_generation, interoperability, releases, portal
from pydantic import Field, StrictStr, field_validator
from typing import Any, Optional
from typing_extensions import Annotated
from api_test.generated.models.error_response import ErrorResponse
from api_test.generated.models.o_auth_authorize_request import OAuthAuthorizeRequest
from api_test.generated.models.o_auth_authorize_response import OAuthAuthorizeResponse
from api_test.generated.models.o_auth_profile_status import OAuthProfileStatus
from api_test.generated.models.o_auth_token_request import OAuthTokenRequest

router = APIRouter()

@router.get(
    "/api/projects/{reference:path}/oauth/profiles/{profile}",
    operation_id="get_oauth_profile_status",
    tags=["oauth",],
    responses={
        200: {"description": "Success", "model": OAuthProfileStatus},400: {"description": "Invalid OAuth request or saved configuration", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Authorization state, issuance ownership or refresh conflict; reconnect if required", "model": ErrorResponse},502: {"description": "Sanitized provider or transport failure", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},504: {"description": "OAuth endpoint timeout", "model": ErrorResponse},
    },
)
async def get_oauth_profile_status(context=Depends(request_context)) -> Response:
    return await context.call(
        oauth.profile_status, [],
        upload=False,

    )

@router.delete(
    "/api/projects/{reference:path}/oauth/profiles/{profile}",
    operation_id="disconnect_oauth_profile",
    tags=["oauth",],
    responses={
        200: {"description": "Success", "model": OAuthProfileStatus},400: {"description": "Invalid OAuth request or saved configuration", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Authorization state, issuance ownership or refresh conflict; reconnect if required", "model": ErrorResponse},502: {"description": "Sanitized provider or transport failure", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},504: {"description": "OAuth endpoint timeout", "model": ErrorResponse},
    },
)
async def disconnect_oauth_profile(context=Depends(request_context)) -> Response:
    return await context.call(
        oauth.disconnect, [],
        upload=False,

    )

@router.post(
    "/api/projects/{reference:path}/oauth/profiles/{profile}/token",
    operation_id="issue_or_refresh_oauth_token",
    tags=["oauth",],
    responses={
        200: {"description": "Success", "model": OAuthProfileStatus},400: {"description": "Invalid OAuth request or saved configuration", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Authorization state, issuance ownership or refresh conflict; reconnect if required", "model": ErrorResponse},502: {"description": "Sanitized provider or transport failure", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},504: {"description": "OAuth endpoint timeout", "model": ErrorResponse},
    },
)
async def issue_or_refresh_oauth_token(context=Depends(request_context)) -> Response:
    return await context.call(
        oauth.token_action, [],
        upload=False,

    )

@router.post(
    "/api/projects/{reference:path}/oauth/profiles/{profile}/authorize",
    operation_id="authorize_oauth_profile",
    tags=["oauth",],
    responses={
        200: {"description": "Success", "model": OAuthAuthorizeResponse},400: {"description": "Invalid OAuth request or saved configuration", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Authorization state, issuance ownership or refresh conflict; reconnect if required", "model": ErrorResponse},502: {"description": "Sanitized provider or transport failure", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},504: {"description": "OAuth endpoint timeout", "model": ErrorResponse},
    },
)
async def authorize_oauth_profile(context=Depends(request_context)) -> Response:
    return await context.call(
        oauth.authorize, [],
        upload=False,

    )

@router.get(
    "/api/oauth/callback/{providerKey}",
    operation_id="complete_oauth_authorization",
    tags=["oauth",],
    responses={
        303: {"description": "Authorization completed; redirects to the trusted Studio project settings without code, state or provider details."},400: {"description": "Invalid OAuth request or saved configuration", "model": ErrorResponse},403: {"description": "Policy denied", "model": ErrorResponse},409: {"description": "Authorization state, issuance ownership or refresh conflict; reconnect if required", "model": ErrorResponse},502: {"description": "Sanitized provider or transport failure", "model": ErrorResponse},503: {"description": "Storage unavailable", "model": ErrorResponse},504: {"description": "OAuth endpoint timeout", "model": ErrorResponse},
    },
)
async def complete_oauth_authorization(context=Depends(request_context)) -> Response:
    return await context.call(
        oauth.callback, [],
        upload=False,

    )
