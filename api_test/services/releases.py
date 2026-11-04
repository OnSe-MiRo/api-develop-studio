"""Workspace-scoped API release management over immutable project revisions."""
from api_test.release_store import ReleaseStore, ReleaseError


def _call(request, studio, operation):
    reference=request.request.path_params['reference']
    studio.ensure_example_project_enabled(reference)
    documents=studio.collaboration_store()
    store=ReleaseStore(documents.database_path,context=documents.context)
    try:
        response=operation(store,reference)
        response.headers["Cache-Control"]="private, no-store"
        response.headers["Vary"]="Cookie, Authorization"
        return response
    except ReleaseError as exc:
        raise studio.ApiError(str(exc),exc.status_code) from exc
    except PermissionError as exc:
        raise studio.ApiError('Workspace 접근 권한이 없습니다.',403) from exc


def list_releases(request, studio):
    def invoke(store,reference):
        try: limit=int(request.query_value('limit') or '20')
        except ValueError as exc: raise studio.ApiError('limit을 확인하세요.') from exc
        return request.json_response(200,store.list(reference,limit=limit,before=request.query_value('before')))
    return _call(request,studio,invoke)


def create_release(request, studio):
    studio.ensure_example_document_writable("projects",request.request.path_params["reference"])
    return _call(request,studio,lambda store,reference: request.json_response(201,store.create(reference,request.read_body())))


def get_release(request, studio):
    return _call(request,studio,lambda store,reference: request.json_response(200,store.detail(reference,request.request.path_params['releaseId'])))


def get_release_source(request, studio):
    return _call(request,studio,lambda store,reference: request.json_response(200,store.source(reference,request.request.path_params['releaseId'])))


def transition_release(request, studio):
    studio.ensure_example_document_writable("projects",request.request.path_params["reference"])
    return _call(request,studio,lambda store,reference: request.json_response(200,store.transition(reference,request.request.path_params['releaseId'],request.read_body())))
