"""Bounded OAuth endpoint transport with pinned DNS, TLS and no redirects."""
from __future__ import annotations

import base64
import http.client
import ipaddress
import json
import os
import socket
import threading
import time
import ssl
from urllib.parse import quote_plus, urlencode, urlsplit


MAX_TOKEN_RESPONSE = 64 * 1024
TIMEOUT_SECONDS = 8


class OAuthTransportError(ValueError):
    pass


class OAuthTimeoutError(OAuthTransportError):
    pass


def _local_mode() -> bool:
    return os.environ.get("LOCAL_SERVER", "").strip().lower() == "true"


def validate_endpoint(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 2048 or any(ord(char) <= 32 or char == "\\" for char in value):
        raise OAuthTransportError("OAuth endpoint URL is invalid")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise OAuthTransportError("OAuth endpoint URL is invalid") from exc
    if not host or parsed.username or parsed.password or parsed.fragment or parsed.scheme not in ("https", "http"):
        raise OAuthTransportError("OAuth endpoint URL is invalid")
    if parsed.scheme == "http" and not (_local_mode() and host in ("localhost", "127.0.0.1", "::1")):
        raise OAuthTransportError("OAuth endpoint must use HTTPS")
    if port is not None and not 1 <= port <= 65535:
        raise OAuthTransportError("OAuth endpoint port is invalid")
    return value


def _pin(value: str):
    parsed = urlsplit(validate_endpoint(value))
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        parsed_addresses = [ipaddress.ip_address(address) for address in addresses]
    except (OSError, ValueError) as exc:
        raise OAuthTransportError("OAuth endpoint DNS resolution failed") from exc
    if not parsed_addresses:
        raise OAuthTransportError("OAuth endpoint DNS resolution failed")
    allow_loopback = _local_mode() and host in ("localhost", "127.0.0.1", "::1")
    if not all(address.is_loopback if allow_loopback else address.is_global for address in parsed_addresses):
        raise OAuthTransportError("OAuth endpoint resolved to a non-public address")
    return parsed, str(parsed_addresses[0]), port


class _PinnedHttps(http.client.HTTPSConnection):
    def __init__(self, host: str, pinned: str, port: int):
        super().__init__(host, port, timeout=TIMEOUT_SECONDS, context=ssl.create_default_context())
        self._pinned = pinned

    def connect(self):
        raw = socket.create_connection((self._pinned, self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


class _PinnedHttp(http.client.HTTPConnection):
    def __init__(self, host: str, pinned: str, port: int):
        super().__init__(host, port, timeout=TIMEOUT_SECONDS)
        self._pinned = pinned

    def connect(self):
        self.sock = socket.create_connection((self._pinned, self.port), self.timeout)


def post_token_form(url: str, fields: dict[str, str], *, client_id: str, client_secret: str | None,
                    method: str) -> dict:
    parsed, pinned, port = _pin(url)
    if method not in ("basic", "post", "none"):
        raise OAuthTransportError("OAuth client authentication method is invalid")
    body = dict(fields)
    if method == "post":
        body.update(client_id=client_id, client_secret=client_secret or "")
    else:
        body["client_id"] = client_id
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json",
               "Cache-Control": "no-store", "Host": parsed.netloc}
    if method == "basic":
        if not client_secret:
            raise OAuthTransportError("OAuth client secret is unavailable")
        credential = base64.b64encode((quote_plus(client_id) + ":" + quote_plus(client_secret)).encode("ascii")).decode("ascii")
        headers["Authorization"] = "Basic " + credential
        body.pop("client_id", None)
    connection = (_PinnedHttps if parsed.scheme == "https" else _PinnedHttp)(parsed.hostname, pinned, port)
    deadline = time.monotonic() + TIMEOUT_SECONDS
    def abort():
        if connection.sock is not None:
            try:
                connection.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
    watchdog = threading.Timer(TIMEOUT_SECONDS, abort)
    watchdog.daemon = True
    watchdog.start()
    try:
        connection.request("POST", (parsed.path or "/") + ("?" + parsed.query if parsed.query else ""),
                           urlencode(body).encode("ascii"), headers)
        response = connection.getresponse()
        content = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            if connection.sock is not None:
                connection.sock.settimeout(remaining)
            chunk = response.read1(min(4096, MAX_TOKEN_RESPONSE + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
            if len(content) > MAX_TOKEN_RESPONSE:
                raise OAuthTransportError("OAuth token response is too large")
        if response.status < 200 or response.status >= 300:
            raise OAuthTransportError("OAuth token endpoint rejected the request")
        if response.getheader("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise OAuthTransportError("OAuth token response is invalid")
        payload = json.loads(bytes(content).decode("utf-8"))
        if not isinstance(payload, dict):
            raise OAuthTransportError("OAuth token response is invalid")
        return payload
    except (TimeoutError, socket.timeout) as exc:
        raise OAuthTimeoutError("OAuth token endpoint timed out") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, http.client.HTTPException) as exc:
        if time.monotonic() >= deadline:
            raise OAuthTimeoutError("OAuth token endpoint timed out") from exc
        raise OAuthTransportError("OAuth token endpoint is unavailable") from exc
    finally:
        watchdog.cancel()
        connection.close()
