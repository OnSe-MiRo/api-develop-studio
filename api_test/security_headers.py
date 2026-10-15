"""Header policy without task/stream buffering or context-variable changes."""
from starlette.datastructures import MutableHeaders


class SecurityHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        async def send_headers(message):
            if message['type'] == 'http.response.start':
                headers = MutableHeaders(scope=message)
                headers.setdefault('X-Frame-Options', 'DENY')
                headers.setdefault('Referrer-Policy', 'no-referrer')
                headers.setdefault('Content-Security-Policy', "frame-ancestors 'none'")
                if scope.get('path', '').startswith(('/api/', '/auth/')):
                    headers.setdefault('Cache-Control', 'no-store')
            await send(message)

        await self.app(scope, receive, send_headers)
