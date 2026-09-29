"""HTTP operations for the load-test result repository."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from api_test.database import database_url
from api_test.load_results import LoadResultError
from api_test.load_test_store import DuplicateRunError, LoadTestStore, MAX_RESPONSE_BYTES


@lru_cache(maxsize=8)
def _cached_store(path, database_url):
    return LoadTestStore(Path(path), url=database_url)


def _store(studio):
    path = os.environ.get("STUDIO_DB_PATH", str(studio.ROOT / "data" / "studio.db"))
    return _cached_store(path, database_url())


def _integer(request, name, default):
    value = request.query_value(name)
    try:
        return int(value) if value is not None else default
    except ValueError as exc:
        raise ValueError(f"Invalid {name}") from exc


def _response(request, studio, result):
    response = request.json_response(200, result)
    if len(response.body) > MAX_RESPONSE_BYTES:
        raise studio.ApiError("Load-test response exceeds 1 MiB; narrow the list or series query. Detail and comparison are never truncated.", status_code=413)
    return response


def create_load_test_run(request, studio):
    try:
        bundle = json.loads(request.body.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite number")))
        if not isinstance(bundle, dict):
            raise ValueError("Result bundle must be an object")
        result = _store(studio).import_bundle(bundle)
    except DuplicateRunError as exc:
        raise studio.ApiError(str(exc), status_code=409) from exc
    except (ValueError, UnicodeError, LoadResultError) as exc:
        raise studio.ApiError(str(exc)) from exc
    return request.json_response(201, result)


def list_load_test_runs(request, studio):
    try:
        result = _store(studio).list_runs(
            project=request.query_value("project") or "",
            scenario=request.query_value("scenario") or "",
            status=request.query_value("status") or "",
            started_from=request.query_value("from") or "",
            started_to=request.query_value("to") or "",
            limit=_integer(request, "limit", 20),
            cursor=request.query_value("cursor") or "")
    except ValueError as exc:
        raise studio.ApiError(str(exc)) from exc
    return _response(request, studio, result)


def get_load_test_run(request, studio):
    run_id = request.request.path_params["runId"]
    result = _store(studio).detail(run_id)
    if result is None:
        raise studio.ApiError("Run not found", status_code=404)
    return _response(request, studio, result)


def get_load_test_series(request, studio):
    run_id = request.request.path_params["runId"]
    try:
        result = _store(studio).series(run_id,
            started_from=request.query_value("from") or "",
            started_to=request.query_value("to") or "",
            max_points=_integer(request, "maxPoints", 500))
    except ValueError as exc:
        raise studio.ApiError(str(exc)) from exc
    if result is None:
        raise studio.ApiError("Run not found", status_code=404)
    return _response(request, studio, result)


def compare_load_test_runs(request, studio):
    baseline = request.query_value("baseline") or ""
    candidate = request.query_value("candidate") or ""
    if not baseline or not candidate:
        raise studio.ApiError("baseline and candidate are required")
    try:
        result = _store(studio).compare(baseline, candidate)
    except ValueError as exc:
        raise studio.ApiError(str(exc)) from exc
    if result is None:
        raise studio.ApiError("Run not found", status_code=404)
    return _response(request, studio, result)
