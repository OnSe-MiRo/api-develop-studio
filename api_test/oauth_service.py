"""OAuth 2.0 profile issuance, PKCE callback and resource-token resolution."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urlsplit, urlunsplit

from fastapi.responses import RedirectResponse

from .oauth_transport import OAuthTimeoutError, OAuthTransportError, post_token_form, validate_endpoint
from .oauth_vault import Lease, OAuthTokenResponseError, OAuthVaultError, Vault
from .project_variables import PROJECT_VARIABLE_PATTERN, ProjectVariableError, decrypt_secret, stored_project_variables
from .request_profiles import select_environment, validate_auth_profiles


class OAuthError(ValueError):
    def __init__(self, message: str, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def _origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
        hostname = parsed.hostname
    except ValueError as exc:
        raise OAuthError("OAuth resource URL is invalid") from exc
    if (parsed.scheme not in ("https", "http") or not hostname or parsed.username or parsed.password or parsed.fragment or
            any(ord(char) <= 32 or char == "\\" for char in value)):
        raise OAuthError("OAuth resource URL is invalid")
    default = 443 if parsed.scheme == "https" else 80
    formatted_host = f"[{hostname.lower()}]" if ":" in hostname else hostname.lower()
    return f"{parsed.scheme}://{formatted_host}" + (f":{port}" if port and port != default else "")


def _local() -> bool:
    return os.environ.get("LOCAL_SERVER", "").strip().lower() == "true"


def _bound_resource(base_url: str, requested_url: str):
    try:
        saved, requested = _origin(base_url), _origin(requested_url)
    except ValueError as exc:
        raise OAuthError("OAuth resource URL is invalid") from exc
    if saved != requested:
        raise OAuthError("OAuth profile token is bound to the saved API origin")
    if not saved.startswith("https://"):
        hostname = urlsplit(saved).hostname
        if not (_local() and hostname in ("localhost", "127.0.0.1", "::1")):
            raise OAuthError("OAuth resource requires HTTPS")
    return saved


def _profile(project: dict, reference: str, environment: str, name: str):
    if not isinstance(environment, str) or len(environment) > 128 or not isinstance(name, str) or not 1 <= len(name) <= 128:
        raise OAuthError("OAuth profile selection is invalid")
    try:
        selected = select_environment(project, environment, use_default=False)
        profiles = selected.get("auth_profiles", {})
        validate_auth_profiles(profiles)
        profile = profiles.get(name)
        if not isinstance(profile, dict) or profile.get("type") != "OAuth 2.0":
            raise OAuthError("Saved OAuth profile is not configured")
        _, encrypted = stored_project_variables(selected, reference)
    except ProjectVariableError as exc:
        raise OAuthError("Saved OAuth profile is invalid") from exc
    return profile, encrypted, selected["base_url"]


def _fingerprint(profile: dict, encrypted: dict, base_url: str, environment: str) -> str:
    secret_ref = profile.get("clientSecret")
    match = PROJECT_VARIABLE_PATTERN.fullmatch(secret_ref) if isinstance(secret_ref, str) else None
    secret_ciphertext = encrypted.get(match.group(1)) if match else None
    if profile["clientAuthMethod"] != "none" and not secret_ciphertext:
        raise OAuthError("OAuth client secret is not configured")
    return hashlib.sha256(json.dumps({"profile": profile, "secretCiphertext": secret_ciphertext,
                                      "apiOrigin": _origin(base_url), "environment": environment},
                                     sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _client_secret(profile: dict, encrypted: dict) -> str | None:
    if profile["clientAuthMethod"] == "none":
        return None
    match = PROJECT_VARIABLE_PATTERN.fullmatch(profile["clientSecret"])
    if not match or match.group(1) not in encrypted:
        raise OAuthError("OAuth client secret is not configured")
    try:
        return decrypt_secret(encrypted[match.group(1)])
    except ProjectVariableError as exc:
        raise OAuthError("OAuth secure storage is unavailable", 503) from exc


def _provider_key(profile: dict) -> str:
    data = "\n".join((profile.get("authorizationUrl", ""), profile["tokenUrl"], profile["clientId"]))
    return hashlib.sha256(data.encode()).hexdigest()[:24]


def _callback_origin(request) -> str:
    configured = os.environ.get("STUDIO_OAUTH_CALLBACK_ORIGIN", "").strip()
    if _local():
        host = request.request.url.hostname
        if host not in ("localhost", "127.0.0.1", "::1"):
            raise OAuthError("OAuth callback host is invalid")
        return _origin(str(request.request.url))
    if not configured or not configured.startswith("https://"):
        raise OAuthError("STUDIO_OAUTH_CALLBACK_ORIGIN must be a trusted HTTPS origin")
    validate_endpoint(configured)
    if configured != _origin(configured):
        raise OAuthError("OAuth callback origin must be an exact HTTPS origin")
    # A trusted TLS terminator can speak HTTP to Uvicorn (proxy_headers=False).
    # Trust only the configured public origin and the preserved Host authority,
    # never Forwarded or X-Forwarded-Proto supplied by the request.
    host = request.headers.get("Host", "")
    if not host or any(ord(char) <= 32 or char in "/\\@" for char in host) or host.lower() != urlsplit(configured).netloc.lower():
        raise OAuthError("OAuth callback Host does not match the configured origin")
    return configured


def _status(vault: Vault, identity, profile: dict, fingerprint: str, callback_uri: str | None):
    return {"configured": True, "grantType": profile["grantType"], "callbackUri": callback_uri,
            **vault.status(identity, fingerprint)}


def _exchange(profile: dict, encrypted: dict, lease: Lease, vault: Vault, *, code=None, verifier=None, callback_uri=None):
    if lease.action == "refresh":
        fields = {"grant_type": "refresh_token", "refresh_token": lease.refresh_token}
    elif lease.action == "authorization_code":
        fields = {"grant_type": "authorization_code", "code": code, "redirect_uri": callback_uri,
                  "code_verifier": verifier}
    else:
        fields = {"grant_type": "client_credentials"}
        if profile.get("scopes"):
            fields["scope"] = " ".join(profile["scopes"])
    try:
        payload = post_token_form(profile["tokenUrl"], fields, client_id=profile["clientId"],
                                  client_secret=_client_secret(profile, encrypted),
                                  method=profile["clientAuthMethod"])
        return vault.finish(lease, payload, public_client=profile["clientAuthMethod"] == "none")
    except (OAuthTransportError, OAuthVaultError, OAuthError, ProjectVariableError, PermissionError) as exc:
        try:
            vault.abort(lease)
        except PermissionError:
            pass
        if isinstance(exc, OAuthTimeoutError):
            raise OAuthError("OAuth token endpoint timed out", 504) from exc
        if isinstance(exc, OAuthTokenResponseError):
            raise OAuthError("OAuth token endpoint returned an invalid response", 502) from exc
        if isinstance(exc, ProjectVariableError):
            raise OAuthError("OAuth secure storage is unavailable", 503) from exc
        if isinstance(exc, OAuthError):
            raise exc
        if isinstance(exc, OAuthVaultError):
            raise OAuthError("OAuth authorization must be reconnected", 409) from exc
        if isinstance(exc, PermissionError):
            raise OAuthError("OAuth action is not permitted", 403) from exc
        raise OAuthError("OAuth token endpoint failed", 502) from exc


def resource_token(reference: str, environment: str, name: str, profile: dict, encrypted: dict,
                   base_url: str, request_url: str) -> str:
    _bound_resource(base_url, request_url)
    fingerprint = _fingerprint(profile, encrypted, base_url, environment)
    from .request_scope import current_context
    vault = Vault(context=current_context())
    identity = vault.identity(reference, environment, name)
    try:
        claim = vault.acquire(identity, fingerprint, profile["grantType"])
    except OAuthVaultError as exc:
        raise OAuthError("OAuth authorization must be connected or refreshed", 409) from exc
    except PermissionError as exc:
        raise OAuthError("OAuth action is not permitted", 403) from exc
    except ProjectVariableError as exc:
        raise OAuthError("OAuth secure storage is unavailable", 503) from exc
    return claim if isinstance(claim, str) else _exchange(profile, encrypted, claim, vault)


def profile_status(request, studio):
    reference, name = request.request.path_params["reference"], request.request.path_params["profile"]
    environment = request.query_value("environment") or ""
    studio.ensure_example_project_enabled(reference)
    current = studio.collaboration_store().get("projects", reference)
    if current is None:
        raise studio.DocumentNotFoundError("Project not found")
    try:
        profile, encrypted, base_url = _profile(current.document, reference, environment, name)
        fingerprint = _fingerprint(profile, encrypted, base_url, environment)
        callback = (_callback_origin(request) + "/api/oauth/callback/" + _provider_key(profile)
                    if profile["grantType"] == "authorization_code" else None)
        vault = Vault(context=studio.collaboration_store().context)
        return request.json_response(200, _status(vault, vault.identity(reference, environment, name), profile, fingerprint, callback))
    except OAuthError as exc:
        raise studio.ApiError(str(exc), status_code=exc.status_code) from exc
    except OAuthVaultError as exc:
        raise studio.ApiError("OAuth authorization must be reconnected", status_code=409) from exc
    except PermissionError as exc:
        raise studio.ApiError("OAuth action is not permitted", status_code=403) from exc


def token_action(request, studio):
    reference, name = request.request.path_params["reference"], request.request.path_params["profile"]
    body = request.read_body()
    environment, action = body.get("environment", ""), body.get("action")
    if action not in ("issue", "refresh"):
        raise studio.ApiError("OAuth action must be issue or refresh")
    studio.ensure_example_project_enabled(reference)
    current = studio.collaboration_store().get("projects", reference)
    if current is None:
        raise studio.DocumentNotFoundError("Project not found")
    try:
        profile, encrypted, base_url = _profile(current.document, reference, environment, name)
        if (action == "issue") != (profile["grantType"] == "client_credentials"):
            raise OAuthError("OAuth action does not match the configured grant")
        fingerprint = _fingerprint(profile, encrypted, base_url, environment)
        vault = Vault(context=studio.collaboration_store().context)
        identity = vault.identity(reference, environment, name)
        claim = vault.acquire(identity, fingerprint, profile["grantType"], force=True)
        if isinstance(claim, str):
            raise OAuthError("OAuth issuance state changed", 409)
        _exchange(profile, encrypted, claim, vault)
        return request.json_response(200, _status(vault, identity, profile, fingerprint, None))
    except OAuthError as exc:
        raise studio.ApiError(str(exc), status_code=exc.status_code) from exc
    except OAuthVaultError as exc:
        raise studio.ApiError("OAuth authorization must be reconnected", status_code=409) from exc
    except PermissionError as exc:
        raise studio.ApiError("OAuth action is not permitted", status_code=403) from exc


def authorize(request, studio):
    reference, name = request.request.path_params["reference"], request.request.path_params["profile"]
    body = request.read_body()
    environment = body.get("environment", "")
    studio.ensure_example_project_enabled(reference)
    current = studio.collaboration_store().get("projects", reference)
    if current is None:
        raise studio.DocumentNotFoundError("Project not found")
    try:
        profile, encrypted, base_url = _profile(current.document, reference, environment, name)
        if profile["grantType"] != "authorization_code":
            raise OAuthError("This OAuth profile does not use authorization_code")
        fingerprint = _fingerprint(profile, encrypted, base_url, environment)
        provider_key = _provider_key(profile)
        callback_uri = _callback_origin(request) + "/api/oauth/callback/" + provider_key
        parsed = urlsplit(validate_endpoint(profile["authorizationUrl"]))
        reserved = {"response_type", "client_id", "redirect_uri", "scope", "state", "code_challenge", "code_challenge_method"}
        query = parse_qsl(parsed.query, keep_blank_values=True)
        if any(key in reserved for key, _ in query):
            raise OAuthError("OAuth authorization URL contains reserved parameters")
        vault = Vault(context=studio.collaboration_store().context)
        state, cookie, verifier = vault.create_pending(vault.identity(reference, environment, name), provider_key,
                                                       fingerprint, callback_uri, request.headers.get("User-Agent", ""))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode("ascii")
        query += [("response_type", "code"), ("client_id", profile["clientId"]), ("redirect_uri", callback_uri),
                  ("state", state), ("code_challenge", challenge), ("code_challenge_method", "S256")]
        if profile.get("scopes"):
            query.append(("scope", " ".join(profile["scopes"])))
        authorization_url = urlunsplit(parsed._replace(query=urlencode(query)))
        response = request.json_response(200, {"authorizationUrl": authorization_url, "callbackUri": callback_uri})
        secure = "; Secure" if callback_uri.startswith("https://") else ""
        response.headers.append("Set-Cookie", f"studio_oauth_state={cookie}; Max-Age=300; Path=/api/oauth/callback/; HttpOnly; SameSite=Lax{secure}")
        return response
    except (OAuthError, OAuthTransportError, OAuthVaultError, PermissionError, ProjectVariableError) as exc:
        status = exc.status_code if isinstance(exc, OAuthError) else 503 if isinstance(exc, ProjectVariableError) else 403 if isinstance(exc, PermissionError) else 409 if isinstance(exc, OAuthVaultError) else 400
        raise studio.ApiError(str(exc) if isinstance(exc, OAuthError) else "OAuth action is not permitted" if status == 403 else "OAuth authorization is unavailable",
                              status_code=status) from exc


def callback(request, studio):
    provider_key = request.request.path_params["providerKey"]
    query = parse_qs(request.request.url.query, keep_blank_values=True)
    state_values, code_values = query.get("state", []), query.get("code", [])
    if len(state_values) != 1 or len(code_values) != 1 or "error" in query or not code_values[0] or len(code_values[0]) > 4096:
        raise studio.ApiError("OAuth callback could not be completed")
    state, code = state_values[0], code_values[0]
    cookies = SimpleCookie()
    try:
        cookies.load(request.headers.get("Cookie", ""))
    except Exception:
        pass
    morsel = cookies.get("studio_oauth_state")
    cookie = morsel.value if morsel else ""
    vault = Vault(context=studio.collaboration_store().context)
    pending = None
    try:
        expected = vault.peek_pending(state, cookie, provider_key, request.headers.get("User-Agent", ""))
        identity = expected["identity"]
        current = studio.collaboration_store().get("projects", identity[2])
        if current is None:
            raise OAuthError("OAuth project changed", 409)
        profile, encrypted, base_url = _profile(current.document, identity[2], identity[3], identity[4])
        if _provider_key(profile) != provider_key or _fingerprint(profile, encrypted, base_url, identity[3]) != expected["configHash"]:
            raise OAuthError("OAuth profile changed", 409)
        if profile.get("issuer") and query.get("iss") != [profile["issuer"]]:
            raise OAuthError("OAuth provider identity changed", 409)
        pending = vault.consume_pending(state, cookie, provider_key, request.headers.get("User-Agent", ""))
        if pending["configHash"] != expected["configHash"] or pending["identity"] != identity:
            raise OAuthError("OAuth browser state changed", 409)
        _exchange(profile, encrypted, pending["lease"], vault, code=code, verifier=pending["verifier"],
                  callback_uri=pending["callbackUri"])
        slug = identity[2].removesuffix(".json")
        response = RedirectResponse("/projects/settings?project=" + quote(slug, safe=""), status_code=303)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers.append("Set-Cookie", "studio_oauth_state=; Max-Age=0; Path=/api/oauth/callback/; HttpOnly; SameSite=Lax")
        return response
    except (OAuthVaultError, OAuthError, PermissionError, ProjectVariableError) as exc:
        if pending is not None:
            try:
                vault.abort(pending["lease"])
            except PermissionError:
                pass
        status = 503 if isinstance(exc, ProjectVariableError) else 403 if isinstance(exc, PermissionError) else 409 if isinstance(exc, OAuthVaultError) else exc.status_code
        raise studio.ApiError("OAuth callback could not be completed", status_code=status) from exc


def disconnect(request, studio):
    reference, name = request.request.path_params["reference"], request.request.path_params["profile"]
    environment = request.query_value("environment") or ""
    current = studio.collaboration_store().get("projects", reference)
    if current is None:
        raise studio.DocumentNotFoundError("Project not found")
    try:
        profile, encrypted, base_url = _profile(current.document, reference, environment, name)
        fingerprint = _fingerprint(profile, encrypted, base_url, environment)
        vault = Vault(context=studio.collaboration_store().context)
        identity = vault.identity(reference, environment, name)
        vault.disconnect(identity)
        return request.json_response(200, _status(vault, identity, profile, fingerprint, None))
    except OAuthError as exc:
        raise studio.ApiError(str(exc), status_code=exc.status_code) from exc
    except OAuthVaultError as exc:
        raise studio.ApiError("OAuth authorization must be reconnected", status_code=409) from exc
    except PermissionError as exc:
        raise studio.ApiError("OAuth action is not permitted", status_code=403) from exc
