"""Server-owned identity and execution scope; never inferred from actor headers."""
from contextlib import contextmanager, closing
from contextvars import ContextVar
from dataclasses import dataclass
import inspect
import os
from pathlib import Path
import uuid
from urllib.parse import urlsplit

from api_test.database import LOCAL_CONTEXT, RequestContext, connect, require_membership

_SCOPE = ContextVar('studio_request_scope', default=LOCAL_CONTEXT)


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    workspace_id: str

    def context(self):
        return RequestContext(self.workspace_id, self.user_id, uuid.uuid4().hex)


def current_context():
    return _SCOPE.get()


@contextmanager
def bind_context(context):
    token = _SCOPE.set(context)
    try:
        yield
    finally:
        _SCOPE.reset(token)


def require_permission(studio, context, permission):
    # Initialize/migrate via the existing local bootstrap, not user-supplied identities.
    studio.collaboration_store()
    path = Path(os.environ.get('STUDIO_DB_PATH', studio.ROOT / 'data' / 'studio.db'))
    with closing(connect(path)) as db:
        role = require_membership(db, context)
    allowed = {
        'read': {'owner', 'admin', 'editor', 'runner', 'viewer'},
        'edit': {'owner', 'admin', 'editor'},
        'run': {'owner', 'admin', 'editor', 'runner'},
        'admin': {'owner', 'admin'},
    }
    if role not in allowed[permission]:
        raise PermissionError('Workspace role does not permit this action')


def permission_for(request):
    path = request.url.path
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return 'read'
    if '/oauth/profiles/' in path and request.method in ('POST', 'DELETE'):
        return 'run'
    if request.method == 'POST':
        if path in ('/api/docs', '/api/interoperability/preview', '/api/interoperability/curl') or path.endswith('/openapi/contract'):
            return 'read'
        if path.startswith('/api/runs/') and path.endswith('/save'):
            return 'run'
        if path.startswith('/api/ownership/') or path.startswith('/api/workspace/'):
            return 'admin'
        if path.rstrip('/') in ('/api/request', '/api/run', '/api/runs', '/api/generate', '/api/generations') or path.endswith('/sdk') or path.endswith(('/cancel', '/rerun', '/mock/start', '/mock/stop', '/mock/reset')):
            return 'run'
    return 'edit'


async def resolve_context(request, studio):
    if not request.url.path.startswith('/api/'):
        return LOCAL_CONTEXT
    provider = getattr(request.app.state, 'current_user_provider', None)
    if provider is None:
        if os.environ.get('STUDIO_AUTH_MODE', 'local') != 'local':
            from api_test.login import service
            from api_test.oidc_client import LoginError
            from starlette.concurrency import run_in_threadpool
            try:
                verified=await run_in_threadpool(lambda:service(request,studio).current_user(request))
                context=verified.context()
            except LoginError as exc:raise studio.ApiError(exc.code,401 if exc.status_code==503 else exc.status_code) from exc
            selected=request.headers.get('X-Studio-Workspace')
            if selected is not None and selected!=context.workspace_id:raise studio.ApiError('인증 문맥과 다른 Workspace에 접근할 수 없습니다.',403)
            return context
        # Local mode is deliberately one fixed workspace. Headers/body cannot switch it.
        if urlsplit('http://' + request.headers.get('Host', '')).hostname not in ('127.0.0.1','localhost','::1'):
            raise studio.ApiError('로컬 인증 모드는 loopback Host만 허용합니다.', 403)
        context = CurrentUser(LOCAL_CONTEXT.user_id,LOCAL_CONTEXT.workspace_id).context()
    else:
        user = provider(request)
        if inspect.isawaitable(user):
            user = await user
        if not isinstance(user, CurrentUser):
            raise studio.ApiError('인증된 사용자 문맥이 필요합니다.', 401)
        try:
            context = user.context()
        except (TypeError, ValueError) as exc:
            raise studio.ApiError('인증된 사용자 문맥이 올바르지 않습니다.', 401) from exc
    selected = request.headers.get('X-Studio-Workspace')
    if selected is not None and selected != context.workspace_id:
        raise studio.ApiError('인증 문맥과 다른 Workspace에 접근할 수 없습니다.', 403)
    return context


def subprocess_environment():
    context = current_context()
    return {**os.environ, 'STUDIO_RUN_WORKSPACE': context.workspace_id,
            'STUDIO_RUN_USER': context.user_id, 'STUDIO_RUN_REQUEST_ID': context.request_id or ''}


def runner_context():
    return RequestContext(os.environ.get('STUDIO_RUN_WORKSPACE', LOCAL_CONTEXT.workspace_id),
                          os.environ.get('STUDIO_RUN_USER', LOCAL_CONTEXT.user_id),
                          os.environ.get('STUDIO_RUN_REQUEST_ID') or None)
