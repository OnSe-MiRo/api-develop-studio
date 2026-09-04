"""Authorization helpers shared by the API runner and one-off requests."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse


class AuthorizationError(ValueError):
    pass


@dataclass(frozen=True)
class AuthorizedRequest:
    url: str
    headers: dict[str, str]


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _required(auth: dict[str, Any], key: str, label: str) -> str:
    value = _text(auth.get(key))
    if not value:
        raise AuthorizationError(f"{label}을(를) 입력하세요.")
    return value


def _add_query(url: str, key: str, value: str) -> str:
    parsed = urlparse(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query.append((key, value))
    return urlunparse(parsed._replace(query=urlencode(query)))


def _oauth_quote(value: str) -> str:
    return quote(value, safe="~-._")


def _oauth1_header(url: str, method: str, auth: dict[str, Any]) -> str:
    consumer_key = _required(auth, "consumerKey", "Consumer Key")
    signature_method = _text(auth.get("signatureMethod")) or "HMAC-SHA256"
    params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": _text(auth.get("nonce")) or uuid.uuid4().hex,
        "oauth_signature_method": signature_method,
        "oauth_timestamp": _text(auth.get("timestamp")) or str(int(time.time())),
        "oauth_version": _text(auth.get("version")) or "1.0",
    }
    access_token = _text(auth.get("accessToken"))
    if access_token:
        params["oauth_token"] = access_token
    callback = _text(auth.get("callback"))
    verifier = _text(auth.get("verifier"))
    if callback:
        params["oauth_callback"] = callback
    if verifier:
        params["oauth_verifier"] = verifier
    parsed = urlparse(url)
    signing_params = list(parse_qsl(parsed.query, keep_blank_values=True)) + list(params.items())
    normalized = "&".join(f"{_oauth_quote(key)}={_oauth_quote(value)}" for key, value in sorted(signing_params))
    base_url = urlunparse(parsed._replace(query="", fragment=""))
    base = "&".join((_oauth_quote(method.upper()), _oauth_quote(base_url), _oauth_quote(normalized)))
    consumer_secret = _text(auth.get("consumerSecret"))
    token_secret = _text(auth.get("tokenSecret"))
    if signature_method == "PLAINTEXT":
        signature = f"{_oauth_quote(consumer_secret)}&{_oauth_quote(token_secret)}"
    else:
        if signature_method not in {"HMAC-SHA1", "HMAC-SHA256"}:
            raise AuthorizationError("OAuth 1.0은 HMAC-SHA1, HMAC-SHA256 또는 PLAINTEXT 서명만 지원합니다.")
        digest = hashlib.sha1 if signature_method == "HMAC-SHA1" else hashlib.sha256
        signing_key = f"{_oauth_quote(consumer_secret)}&{_oauth_quote(token_secret)}".encode()
        signature = base64.b64encode(hmac.new(signing_key, base.encode(), digest).digest()).decode()
    params["oauth_signature"] = signature
    realm = _text(auth.get("realm"))
    items = ([('realm', realm)] if realm else []) + sorted(params.items())
    return "OAuth " + ", ".join(f'{_oauth_quote(key)}="{_oauth_quote(value)}"' for key, value in items)


def _hawk_header(url: str, method: str, auth: dict[str, Any], payload: bytes | None) -> str:
    identifier = _required(auth, "id", "Hawk Auth ID")
    key = _required(auth, "key", "Hawk Auth Key")
    algorithm = _text(auth.get("algorithm")) or "sha256"
    if algorithm not in {"sha1", "sha256"}:
        raise AuthorizationError("Hawk Algorithm은 sha1 또는 sha256이어야 합니다.")
    parsed = urlparse(url)
    timestamp = _text(auth.get("timestamp")) or str(int(time.time()))
    nonce = _text(auth.get("nonce")) or uuid.uuid4().hex[:8]
    ext = _text(auth.get("ext"))
    payload_hash = ""
    if auth.get("includePayloadHash") and payload is not None:
        content_type = _text(auth.get("contentType")) or "application/json"
        normalized_payload = f"hawk.1.payload\n{content_type.lower()}\n{payload.decode('utf-8')}\n".encode()
        payload_hash = base64.b64encode(getattr(hashlib, algorithm)(normalized_payload).digest()).decode()
    normalized = "\n".join(("hawk.1.header", timestamp, nonce, method.upper(), parsed.path or "/", parsed.netloc, str(parsed.port or (443 if parsed.scheme == "https" else 80)), payload_hash, ext, "", ""))
    mac = base64.b64encode(hmac.new(key.encode(), normalized.encode(), getattr(hashlib, algorithm)).digest()).decode()
    values = {"id": identifier, "ts": timestamp, "nonce": nonce, "mac": mac}
    if payload_hash:
        values["hash"] = payload_hash
    for source, target in (("user", "user"), ("ext", "ext"), ("app", "app"), ("dlg", "dlg")):
        if _text(auth.get(source)):
            values[target] = _text(auth[source])
    return "Hawk " + ", ".join(f'{key}="{value}"' for key, value in values.items())


def _aws_header(url: str, method: str, headers: dict[str, str], payload: bytes | None, auth: dict[str, Any]) -> dict[str, str]:
    access_key = _required(auth, "accessKey", "Access Key")
    secret_key = _required(auth, "secretKey", "Secret Key")
    region = _text(auth.get("region")) or "us-east-1"
    service = _required(auth, "service", "Service Name")
    now = time.gmtime()
    amz_date = time.strftime("%Y%m%dT%H%M%SZ", now)
    date_stamp = time.strftime("%Y%m%d", now)
    parsed = urlparse(url)
    result = {key: value for key, value in headers.items()}
    result.setdefault("Host", parsed.netloc)
    result["X-Amz-Date"] = amz_date
    session_token = _text(auth.get("sessionToken"))
    if session_token:
        result["X-Amz-Security-Token"] = session_token
    payload_hash = hashlib.sha256(payload or b"").hexdigest()
    canonical_headers = "".join(f"{key.lower()}:{' '.join(value.strip().split())}\n" for key, value in sorted(result.items(), key=lambda item: item[0].lower()))
    signed_headers = ";".join(key.lower() for key in sorted(result, key=str.lower))
    canonical_query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    canonical_request = "\n".join((method.upper(), parsed.path or "/", canonical_query, canonical_headers, signed_headers, payload_hash))
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(("AWS4-HMAC-SHA256", amz_date, credential_scope, hashlib.sha256(canonical_request.encode()).hexdigest()))
    def sign(key: bytes, message: str) -> bytes:
        return hmac.new(key, message.encode(), hashlib.sha256).digest()
    signing_key = sign(sign(sign(sign(("AWS4" + secret_key).encode(), date_stamp), region), service), "aws4_request")
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    result["Authorization"] = f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"
    return result


def authorization_sensitive_values(auth: object) -> set[str]:
    if not isinstance(auth, dict):
        return set()
    return {_text(value) for key, value in auth.items() if any(part in key.lower() for part in ("token", "secret", "password", "key")) and _text(value)}


def apply_authorization(url: str, method: str, headers: dict[str, str], auth: object, payload: bytes | None = None) -> AuthorizedRequest:
    """Add the supported Postman-style authorization values to an HTTP request."""
    if not isinstance(auth, dict):
        return AuthorizedRequest(url, headers)
    auth_type = _text(auth.get("type")) or "No Auth"
    result_headers = dict(headers)
    if auth_type == "No Auth":
        return AuthorizedRequest(url, result_headers)
    if auth_type == "API Key":
        key, value = _required(auth, "key", "Key"), _required(auth, "value", "Value")
        return AuthorizedRequest(_add_query(url, key, value) if auth.get("addTo") == "Query Params" else url, result_headers if auth.get("addTo") == "Query Params" else {**result_headers, key: value})
    if auth_type in {"Bearer Token", "OAuth 2.0", "JWT Bearer", "ASAP (Atlassian)"}:
        token = _required(auth, "token", "Token")
        prefix = _text(auth.get("headerPrefix")) or "Bearer"
        if auth.get("addTo") == "Query Params":
            return AuthorizedRequest(_add_query(url, _text(auth.get("key")) or "access_token", token), result_headers)
        result_headers["Authorization"] = f"{prefix} {token}"
        return AuthorizedRequest(url, result_headers)
    if auth_type == "Basic Auth":
        username, password = _required(auth, "username", "Username"), _required(auth, "password", "Password")
        result_headers["Authorization"] = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        return AuthorizedRequest(url, result_headers)
    if auth_type == "OAuth 1.0":
        result_headers["Authorization"] = _oauth1_header(url, method, auth)
        return AuthorizedRequest(url, result_headers)
    if auth_type == "Hawk Authentication":
        result_headers["Authorization"] = _hawk_header(url, method, auth, payload)
        return AuthorizedRequest(url, result_headers)
    if auth_type == "AWS Signature":
        return AuthorizedRequest(url, _aws_header(url, method, result_headers, payload, auth))
    if auth_type == "Akamai EdgeGrid":
        client_token, access_token, client_secret = _required(auth, "clientToken", "Client Token"), _required(auth, "accessToken", "Access Token"), _required(auth, "clientSecret", "Client Secret")
        timestamp = time.strftime("%Y%m%dT%H:%M:%S+0000", time.gmtime())
        nonce = uuid.uuid4().hex
        parsed = urlparse(url)
        auth_data = f'EG1-HMAC-SHA256 client_token={client_token};access_token={access_token};timestamp={timestamp};nonce={nonce};'
        data_to_sign = "\t".join((method.upper(), f"{parsed.scheme}://{parsed.netloc}{parsed.path}", "", "", auth_data))
        signing_key = base64.b64encode(hmac.new(client_secret.encode(), timestamp.encode(), hashlib.sha256).digest())
        signature = base64.b64encode(hmac.new(signing_key, data_to_sign.encode(), hashlib.sha256).digest()).decode()
        result_headers["Authorization"] = auth_data + f"signature={signature}"
        return AuthorizedRequest(url, result_headers)
    if auth_type == "Digest Auth":
        _required(auth, "username", "Username")
        _required(auth, "password", "Password")
        return AuthorizedRequest(url, result_headers)
    if auth_type == "NTLM Authentication":
        _required(auth, "username", "Username")
        _required(auth, "password", "Password")
        return AuthorizedRequest(url, result_headers)
    raise AuthorizationError(f"지원하지 않는 Authorization Type입니다: {auth_type}")
