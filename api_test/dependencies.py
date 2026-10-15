"""Request-scoped transport policy shared by generated routes."""
from fastapi import Request
import re
from api_test.database import LOCAL_CONTEXT
from starlette.concurrency import run_in_threadpool
from api_test.request_scope import bind_context, resolve_context, require_permission, permission_for


class RequestContext:
    def __init__(self, request: Request, context, *, public=False):
        self.public = public
        self.context = context
        self.request = request
        self.studio = request.app.state.studio
        self.transport = self.studio.StudioRequest(request, b'')
        self.transport.context = context
        request.state.studio = self.transport
        self.transport.check_request_origin()

    async def call(self, implementation, arguments=(), *, upload=False):
        if self.request.method == "POST" and (self.request.url.path in ("/api/runs", "/api/load-tests/runs") or self.request.url.path.startswith(("/api/session/", "/api/workspace/", "/api/interoperability/")) or re.search(r"/(?:releases|portal)(?:/[^/]+/(?:transition|sdk|sdk/[^/]+/purge))?/?$", self.request.url.path) or (self.request.url.path.startswith("/api/executions/") and self.request.url.path.endswith("/rerun"))):
            chunks, size = [], 0
            async for chunk in self.request.stream():
                size += len(chunk)
                maximum = 4 * 1024 * 1024 if self.request.url.path == "/api/load-tests/runs" else 1024 * 1024
                if size > maximum:
                    raise self.studio.ApiError("요청 본문 크기 제한을 초과했습니다.", status_code=413)
                chunks.append(chunk)
            self.transport.body = b"".join(chunks)
        elif upload:
            chunks, size = [], 0
            async for chunk in self.request.stream():
                size += len(chunk)
                if size > self.studio.MAX_UPLOAD_BYTES:
                    raise self.studio.ApiError('Upload size must be between 1 byte and 25 MB')
                chunks.append(chunk)
            self.transport.body = b''.join(chunks)
        elif self.request.method in {'POST', 'PUT'}:
            self.transport.body = await self.request.body()
        def invoke():
            with bind_context(self.context):
                if self.request.url.path.startswith('/api/') and not self.public:
                    require_permission(self.studio, self.context, permission_for(self.request))
                return implementation(self.transport, self.studio, *arguments)
        return await run_in_threadpool(invoke)


async def request_context(request: Request) -> RequestContext:
    return RequestContext(request, await resolve_context(request, request.app.state.studio))


async def public_request_context(request: Request) -> RequestContext:
    return RequestContext(request, LOCAL_CONTEXT, public=True)
