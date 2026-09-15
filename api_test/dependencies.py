"""Request-scoped transport policy shared by generated routes."""
from fastapi import Request
from starlette.concurrency import run_in_threadpool


class RequestContext:
    def __init__(self, request: Request):
        self.request = request
        self.studio = request.app.state.studio
        self.transport = self.studio.StudioRequest(request, b'')
        request.state.studio = self.transport
        self.transport.check_request_origin()

    async def call(self, implementation, arguments=(), *, upload=False):
        if self.request.url.path == "/api/runs" and self.request.method == "POST":
            chunks, size = [], 0
            async for chunk in self.request.stream():
                size += len(chunk)
                if size > 1024 * 1024:
                    raise self.studio.ApiError("실행 요청은 1 MiB 이하여야 합니다.", status_code=413)
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
        return await run_in_threadpool(implementation, self.transport, self.studio, *arguments)


async def request_context(request: Request) -> RequestContext:
    return RequestContext(request)
