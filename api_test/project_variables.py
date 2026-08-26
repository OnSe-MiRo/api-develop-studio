from __future__ import annotations

import os
import re
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet, InvalidToken


ENCRYPTION_KEY_ENV = "API_TEST_ENCRYPTION_KEY"
ENCRYPTION_SERVICE_URL_ENV = "API_TEST_ENCRYPTION_URL"
VARIABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
PROJECT_VARIABLE_PATTERN = re.compile(r"\{\{project\.([A-Za-z_][A-Za-z0-9_-]*)\}\}")
CASE_VARIABLE_PATTERN = re.compile(r"\{\{case\.([A-Za-z_][A-Za-z0-9_-]*)\}\}")


class ProjectVariableError(ValueError):
    pass


def _fernet() -> Fernet:
    key = os.environ.get(ENCRYPTION_KEY_ENV, "").strip()
    if not key:
        raise ProjectVariableError(
            f"{ENCRYPTION_KEY_ENV} is required to save or use encrypted project variables"
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise ProjectVariableError(
            f"{ENCRYPTION_KEY_ENV} must be a valid Fernet key"
        ) from exc


def _encryption_service_url() -> str:
    return os.environ.get(ENCRYPTION_SERVICE_URL_ENV, "").strip().rstrip("/")


def _service_request(action: str, field: str, value: str) -> str:
    service_url = _encryption_service_url()
    request = Request(
        f"{service_url}/v1/{action}",
        data=json.dumps({field: value}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectVariableError("Encryption service is unavailable") from exc
    result = payload.get("token" if action == "encrypt" else "value") if isinstance(payload, dict) else None
    if not isinstance(result, str) or not result:
        raise ProjectVariableError("Encryption service returned an invalid response")
    return result


def encrypt_secret(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProjectVariableError("Encrypted project variable values must be non-empty strings")
    if _encryption_service_url():
        return _service_request("encrypt", "value", value)
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    if not isinstance(token, str) or not token:
        raise ProjectVariableError("Stored encrypted project variable is invalid")
    if _encryption_service_url():
        return _service_request("decrypt", "token", token)
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeEncodeError, UnicodeDecodeError) as exc:
        raise ProjectVariableError(
            "Cannot decrypt a project variable. Check API_TEST_ENCRYPTION_KEY."
        ) from exc


def _validate_variable_name(name: object) -> str:
    if not isinstance(name, str) or not VARIABLE_NAME_PATTERN.fullmatch(name):
        raise ProjectVariableError(
            "Project variable names must start with a letter or underscore and contain only letters, numbers, _ or -"
        )
    return name


def normalize_project_variables(
    payload: object,
    existing: object | None = None,
) -> dict[str, dict[str, str]]:
    """Convert the project-settings payload into the encrypted on-disk representation."""
    if not isinstance(payload, dict):
        raise ProjectVariableError("project.variables must be an object")
    plain_payload = payload.get("plain", {})
    secret_payload = payload.get("secret", {})
    if not isinstance(plain_payload, dict):
        raise ProjectVariableError("project.variables.plain must be an object")
    if not isinstance(secret_payload, dict):
        raise ProjectVariableError("project.variables.secret must be an object")

    plain: dict[str, str] = {}
    for raw_name, value in plain_payload.items():
        name = _validate_variable_name(raw_name)
        if not isinstance(value, str):
            raise ProjectVariableError(f"Plain project variable {name} must be a string")
        plain[name] = value

    existing_secret: dict[str, str] = {}
    if isinstance(existing, dict) and isinstance(existing.get("secret"), dict):
        existing_secret = {
            name: token for name, token in existing["secret"].items()
            if isinstance(name, str) and isinstance(token, str)
        }

    secret: dict[str, str] = {}
    for raw_name, definition in secret_payload.items():
        name = _validate_variable_name(raw_name)
        if not isinstance(definition, dict):
            raise ProjectVariableError(f"Encrypted project variable {name} must be an object")
        if definition.get("preserve") is True:
            token = existing_secret.get(name)
            if not token:
                raise ProjectVariableError(f"Encrypted project variable {name} has no stored value to preserve")
            secret[name] = token
            continue
        value = definition.get("value")
        if not isinstance(value, str) or not value:
            raise ProjectVariableError(f"Encrypted project variable {name} needs a non-empty value")
        secret[name] = encrypt_secret(value)

    duplicate_names = sorted(set(plain) & set(secret))
    if duplicate_names:
        raise ProjectVariableError(
            f"Project variable names cannot be both plain and encrypted: {', '.join(duplicate_names)}"
        )
    return {"plain": plain, "secret": secret}


def project_variables_for_client(project: dict[str, Any]) -> dict[str, Any]:
    """Return a project document that exposes encrypted variable names but never their values."""
    result = dict(project)
    variables = project.get("variables", {})
    plain = variables.get("plain", {}) if isinstance(variables, dict) else {}
    secret = variables.get("secret", {}) if isinstance(variables, dict) else {}
    result["variables"] = {
        "plain": dict(plain) if isinstance(plain, dict) else {},
        "secret": {
            name: {"configured": True}
            for name in secret
            if isinstance(name, str)
        } if isinstance(secret, dict) else {},
    }
    return result


def normalize_case_variables(payload: object, existing: object | None = None) -> dict[str, dict[str, str]]:
    """Convert a case's submitted secret variables into encrypted storage values."""
    if not isinstance(payload, dict):
        raise ProjectVariableError("case.variables must be an object")
    secret_payload = payload.get("secret", {})
    if not isinstance(secret_payload, dict):
        raise ProjectVariableError("case.variables.secret must be an object")
    existing_secret = {}
    if isinstance(existing, dict) and isinstance(existing.get("secret"), dict):
        existing_secret = {
            name: token for name, token in existing["secret"].items()
            if isinstance(name, str) and isinstance(token, str)
        }
    secret: dict[str, str] = {}
    for raw_name, definition in secret_payload.items():
        name = _validate_variable_name(raw_name)
        if not isinstance(definition, dict):
            raise ProjectVariableError(f"Case secret variable {name} must be an object")
        if definition.get("preserve") is True:
            token = existing_secret.get(name)
            if not token:
                raise ProjectVariableError(f"Case secret variable {name} has no stored value to preserve")
            secret[name] = token
            continue
        value = definition.get("value")
        if not isinstance(value, str) or not value:
            raise ProjectVariableError(f"Case secret variable {name} needs a non-empty value")
        secret[name] = encrypt_secret(value)
    return {"secret": secret}


def case_variables_for_client(case: dict[str, Any]) -> dict[str, Any]:
    """Return a case document without exposing encrypted variable values."""
    result = dict(case)
    variables = case.get("variables", {})
    secret = variables.get("secret", {}) if isinstance(variables, dict) else {}
    result["variables"] = {
        "secret": {
            name: {"configured": True}
            for name in secret
            if isinstance(name, str)
        } if isinstance(secret, dict) else {},
    }
    return result


def stored_project_variables(project: dict[str, Any], reference: str) -> tuple[dict[str, str], dict[str, str]]:
    """Validate and return the plain and encrypted variable maps stored in a project."""
    variables = project.get("variables", {})
    if not isinstance(variables, dict):
        raise ProjectVariableError(f"project.variables must be an object: {reference}")
    plain_value = variables.get("plain", {})
    secret_value = variables.get("secret", {})
    if not isinstance(plain_value, dict) or not isinstance(secret_value, dict):
        raise ProjectVariableError(f"project.variables plain and secret must be objects: {reference}")

    plain: dict[str, str] = {}
    secret: dict[str, str] = {}
    for raw_name, value in plain_value.items():
        name = _validate_variable_name(raw_name)
        if not isinstance(value, str):
            raise ProjectVariableError(f"Plain project variable {name} must be a string: {reference}")
        plain[name] = value
    for raw_name, token in secret_value.items():
        name = _validate_variable_name(raw_name)
        if not isinstance(token, str) or not token:
            raise ProjectVariableError(f"Encrypted project variable {name} is invalid: {reference}")
        secret[name] = token
    duplicate_names = sorted(set(plain) & set(secret))
    if duplicate_names:
        raise ProjectVariableError(
            f"Project variable names cannot be both plain and encrypted: {', '.join(duplicate_names)}"
        )
    return plain, secret


def stored_case_variables(case: dict[str, Any], reference: str) -> dict[str, str]:
    """Validate and return the encrypted variables stored on one API case."""
    variables = case.get("variables", {})
    if not isinstance(variables, dict):
        raise ProjectVariableError(f"case.variables must be an object: {reference}")
    secret_value = variables.get("secret", {})
    if not isinstance(secret_value, dict):
        raise ProjectVariableError(f"case.variables.secret must be an object: {reference}")
    secret: dict[str, str] = {}
    for raw_name, token in secret_value.items():
        name = _validate_variable_name(raw_name)
        if not isinstance(token, str) or not token:
            raise ProjectVariableError(f"Case secret variable {name} is invalid: {reference}")
        secret[name] = token
    return secret


def resolve_project_references(
    value: Any,
    plain: dict[str, str],
    encrypted: dict[str, str],
) -> tuple[Any, set[str]]:
    """Replace {{project.NAME}} references recursively and report secret values for log redaction."""
    cache: dict[str, str] = {}
    used_secrets: set[str] = set()

    def variable(name: str) -> str:
        if name in plain:
            return plain[name]
        if name in encrypted:
            if name not in cache:
                cache[name] = decrypt_secret(encrypted[name])
            used_secrets.add(cache[name])
            return cache[name]
        raise ProjectVariableError(f"Project variable is not defined: {name}")

    def visit(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: visit(child) for key, child in item.items()}
        if isinstance(item, list):
            return [visit(child) for child in item]
        if not isinstance(item, str):
            return item
        match = PROJECT_VARIABLE_PATTERN.fullmatch(item)
        if match:
            return variable(match.group(1))
        return PROJECT_VARIABLE_PATTERN.sub(lambda found: variable(found.group(1)), item)

    return visit(value), used_secrets


def resolve_case_references(value: Any, encrypted: dict[str, str]) -> tuple[Any, set[str]]:
    """Replace {{case.NAME}} references and return values that must be redacted from logs."""
    cache: dict[str, str] = {}
    used_secrets: set[str] = set()

    def variable(name: str) -> str:
        if name not in encrypted:
            raise ProjectVariableError(f"Case variable is not defined: {name}")
        if name not in cache:
            cache[name] = decrypt_secret(encrypted[name])
        used_secrets.add(cache[name])
        return cache[name]

    def visit(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: visit(child) for key, child in item.items()}
        if isinstance(item, list):
            return [visit(child) for child in item]
        if not isinstance(item, str):
            return item
        match = CASE_VARIABLE_PATTERN.fullmatch(item)
        if match:
            return variable(match.group(1))
        return CASE_VARIABLE_PATTERN.sub(lambda found: variable(found.group(1)), item)

    return visit(value), used_secrets
