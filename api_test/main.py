"""Application composition for the generated Studio API."""
from __future__ import annotations
import json
import os
import subprocess
from copy import deepcopy
from contextlib import asynccontextmanager
from starlette.concurrency import run_in_threadpool
from api_test.jobs import JobManager, JobError
from pathlib import Path
import yaml
import uvicorn
from fastapi import APIRouter, FastAPI, Depends
from fastapi.exceptions import RequestValidationError
from api_test.database import DATABASE_ERRORS
from api_test.dependencies import request_context


def resolve_openapi_refs(value, source_path: Path, cache=None):
    """Resolve local external refs so the published contract is self-contained."""
    cache = {} if cache is None else cache
    if isinstance(value, list):
        return [resolve_openapi_refs(item, source_path, cache) for item in value]
    if not isinstance(value, dict):
        return value
    reference = value.get('$ref')
    if isinstance(reference, str):
        file_part, _, fragment = reference.partition('#')
        target_path = (source_path.parent / file_part).resolve() if file_part else source_path
        if target_path not in cache:
            cache[target_path] = yaml.safe_load(target_path.read_text(encoding='utf-8'))
        target = cache[target_path]
        for segment in (fragment[1:].split('/') if fragment.startswith('/') else []):
            segment = segment.replace('~1', '/').replace('~0', '~')
            target = target[segment]
        resolved = resolve_openapi_refs(target, target_path, cache)
        siblings = {key: item for key, item in value.items() if key != '$ref'}
        if siblings and isinstance(resolved, dict):
            resolved = {**resolved, **resolve_openapi_refs(siblings, source_path, cache)}
        return resolved
    return {key: resolve_openapi_refs(item, source_path, cache) for key, item in value.items()}


def public_openapi_spec(path: Path) -> dict:
    specification = yaml.safe_load(path.read_text(encoding='utf-8'))
    resolved = resolve_openapi_refs(specification, path)
    for path_item in resolved.get('paths', {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict):
                for key in list(operation):
                    if key.startswith('x-studio-'):
                        del operation[key]
    return resolved


def create_app(studio) -> FastAPI:
    manager = JobManager.from_environment()

    @asynccontextmanager
    async def lifespan(app):
        if app.state.jobs.closed:
            app.state.jobs = JobManager.from_environment()
        try:
            yield
        finally:
            await run_in_threadpool(app.state.jobs.close)

    app = FastAPI(lifespan=lifespan, title="API Develop Studio", docs_url=None, redoc_url=None,
                  openapi_url="/api/schema.json", redirect_slashes=False)
    app.state.studio = studio
    app.state.jobs = manager
    def error_response(request, exc):
        context = getattr(request.state, "studio", None) or studio.StudioRequest(request, b"")
        status, payload = 400, {"error": str(exc)}
        if isinstance(exc, RequestValidationError):
            payload = {"error": "Invalid request JSON"}
        elif isinstance(exc, (studio.RevisionConflictError, studio.RevisionRequiredError)) and request.method in {"PUT", "POST"}:
            status, payload = 409, {"error": str(exc), "currentRevision": exc.current_revision}
        elif isinstance(exc, subprocess.TimeoutExpired):
            status = 504
            payload = {"error": "OpenAPI 클라이언트 생성 시간이 300초를 초과했습니다." if request.url.path == "/api/generate" else "Test run timed out after 300 seconds"}
            if getattr(exc, "run_id", None):
                payload["runId"] = exc.run_id
        elif isinstance(exc, studio.OwnershipError) and request.method == "POST":
            status, payload = 403, {"error": str(exc), "code": "OWNERSHIP_POLICY_DENIED"}
        elif isinstance(exc, studio.ApiError) and request.method == "POST":
            status = exc.status_code
        if isinstance(exc, JobError):
            status = exc.status_code
        if isinstance(exc, DATABASE_ERRORS):
            status, payload = 503, {"error": "저장소에 연결할 수 없습니다. 잠시 후 다시 시도하세요."}
        return context.json_response(status, payload)

    for error in (JobError, studio.ApiError, studio.OwnershipError, studio.CollaborationStoreError,
                  OSError, json.JSONDecodeError, subprocess.TimeoutExpired, RequestValidationError, *DATABASE_ERRORS):
        app.add_exception_handler(error, error_response)

    from api_test.generated.main import routers
    combined = APIRouter()
    for router in routers:
        combined.routes.extend(router.routes)
    # Register suffix operations before greedy document references across all tags.
    combined.routes.sort(key=lambda route: (route.path.endswith(':path}'), -len(route.path)))
    app.include_router(combined)

    def frontend(request, studio):
        return request.frontend_response()

    def unknown(request, studio):
        messages = {"POST": "Unknown run endpoint", "PUT": "Unknown save endpoint", "DELETE": "Unknown delete endpoint"}
        raise studio.ApiError(messages[request.command])

    @app.get('/{reference:path}', include_in_schema=False)
    async def frontend_route(context=Depends(request_context)):
        return await context.call(frontend)

    @app.api_route('/{reference:path}', methods=['POST', 'PUT', 'DELETE'], include_in_schema=False)
    async def unknown_route(context=Depends(request_context)):
        return await context.call(unknown)

    # Publish the canonical contract rather than reverse engineering opaque request context.
    specification_path = Path(__file__).resolve().parents[1] / 'openapi/studio.yaml'
    public_spec = public_openapi_spec(specification_path)
    app.openapi = lambda: deepcopy(public_spec)
    return app


from api_test.services import studio
app = create_app(studio)
studio.app = app


def run():
    host = os.environ.get('API_TEST_HOST', '127.0.0.1')
    if studio.local_policy()['local_server'] and host not in ('127.0.0.1', '::1', 'localhost'):
        raise SystemExit('LOCAL_SERVER=true에서는 loopback 주소로만 실행할 수 있습니다.')
    uvicorn.run(app, host=host, port=int(os.environ.get('API_TEST_PORT', '8765')), workers=1, proxy_headers=False)


if __name__ == '__main__':
    run()
