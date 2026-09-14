"""FastAPI HTTP contract and thread-pool boundary for synchronous Studio services."""
from __future__ import annotations

import json
import re
import subprocess

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.concurrency import run_in_threadpool

from api_test.routes import dashboard, documents, execution, openapi
from api_test.database import DATABASE_ERRORS


def create_app(studio) -> FastAPI:
    # Existing SPA routes include /docs. Do not claim them for Swagger UI.
    app = FastAPI(title="API Develop Studio", docs_url=None, redoc_url=None,
                  openapi_url="/api/schema.json", redirect_slashes=False)

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
        if isinstance(exc, DATABASE_ERRORS):
            status, payload = 503, {"error": "저장소에 연결할 수 없습니다. 잠시 후 다시 시도하세요."}
        return context.json_response(status, payload)

    for error in (studio.ApiError, studio.OwnershipError, studio.CollaborationStoreError,
                  OSError, json.JSONDecodeError, subprocess.TimeoutExpired, RequestValidationError, *DATABASE_ERRORS):
        app.add_exception_handler(error, error_response)

    def register(path, method, operation, parts=None, *, upload=False, schema=True):
        async def endpoint(request: Request):
            context = studio.StudioRequest(request, b"")
            request.state.studio = context
            context.check_request_origin()
            if upload:
                # Bound the stream before buffering, including chunked uploads.
                chunks, size = [], 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > studio.MAX_UPLOAD_BYTES:
                        raise studio.ApiError("Upload size must be between 1 byte and 25 MB")
                    chunks.append(chunk)
                context.body = b"".join(chunks)
            elif method in {"POST", "PUT"}:
                context.body = await request.body()
            route_parts = list(parts or [])
            if "reference" in request.path_params:
                route_parts.append(request.path_params["reference"])
            if path.endswith("/revisions"):
                route_parts.append("revisions")
            if path.endswith("/openapi/operations"):
                route_parts.extend(["openapi", "operations"])
            return await run_in_threadpool(operation, context, route_parts, studio)

        extra = {"parameters": [{"name": name, "in": "path", "required": True, "schema": {"type": "string"}}
                                for name in re.findall(r"\{([^}:]+)(?::path)?\}", path)]}
        if method in {"POST", "PUT"}:
            media = "application/octet-stream" if upload else "application/json"
            extra.update({"requestBody": {"required": True, "content": {media: {"schema": {"type": "string", "format": "binary"} if upload else {"type": "object"}}}}})
        app.add_api_route(path, endpoint, methods=[method], include_in_schema=schema,
                          name=f"{method.lower()}_{path}", openapi_extra=extra)
        if not path.endswith("{reference:path}"):
            app.add_api_route(path + "/", endpoint, methods=[method], include_in_schema=False)

    register("/api/dashboard", "GET", dashboard.handle_get, ["api", "dashboard"])
    # More-specific suffix routes must precede greedy document references.
    register("/api/projects/{reference:path}/openapi/operations", "POST", openapi.handle_post, ["api", "projects"])
    for kind in ("projects", "cases", "pipelines"):
        prefix = f"/api/{kind}"
        register(prefix, "GET", documents.handle_get, ["api", kind])
        register(prefix + "/{reference:path}/revisions", "GET", documents.handle_get, ["api", kind])
        for method, operation in (("GET", documents.handle_get), ("PUT", documents.handle_put), ("DELETE", documents.handle_delete)):
            register(prefix + "/{reference:path}", method, operation, ["api", kind])

    for path, operation in (("docs", openapi.handle_post), ("generate", openapi.handle_post),
                            ("request", execution.handle_post), ("run", execution.handle_post)):
        register("/api/" + path, "POST", operation, ["api", path])

    def ownership_status(context, parts, studio):
        context.ownership_session(create=True)
        project = context.query_value("project")
        stored = studio.collaboration_store().get("projects", project or "")
        if not stored:
            raise studio.OwnershipError("저장된 프로젝트를 선택하세요.")
        return context.json_response(200, studio.OwnershipStore().status(project, stored.document))

    def ownership_action(context, parts, studio):
        return context.ownership_action(context.api_path())

    register("/api/ownership", "GET", ownership_status)
    register("/api/ownership", "POST", ownership_action)
    register("/api/ownership/{action:path}", "POST", ownership_action)

    def upload_file(context, parts, studio):
        path = studio.safe_attachment_file(studio.CASE_ROOT, parts[2])
        content = context.read_upload()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return context.json_response(200, {"path": path.relative_to(studio.CASE_ROOT).as_posix()})

    register("/api/uploads/{reference:path}", "POST", upload_file, ["api", "uploads"], upload=True)

    def example(context, parts, studio):
        return context.example_response()

    for method in ("GET", "POST"):
        register("/example-api", method, example)
        register("/example-api/{reference:path}", method, example)

    def frontend(context, parts, studio):
        return context.frontend_response()

    def unknown(context, parts, studio):
        message = {"POST": "Unknown run endpoint", "PUT": "Unknown save endpoint", "DELETE": "Unknown delete endpoint"}
        raise studio.ApiError(message[context.command])

    register("/{reference:path}", "GET", frontend, schema=False)
    for method in ("POST", "PUT", "DELETE"):
        register("/{reference:path}", method, unknown, schema=False)
    return app
