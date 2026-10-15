"""Shared-job SDK generation submit/download and synchronous ZIP compatibility."""
from __future__ import annotations

import threading
from fastapi.responses import Response

from api_test.sdk_generation import execute_snapshot, initial_metadata, snapshot_project


class _ArtifactResponse(Response):
    def __init__(self, content, filename, manager, lease_id):
        super().__init__(content, media_type='application/zip',
                         headers={'Content-Disposition': f'attachment; filename="{filename}"',
                                  'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
        self._manager, self._lease_id = manager, lease_id

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Covers response cancellation before send or body iteration.
            self._manager.release_artifact(self._lease_id)


def submit_generation(request, studio):
    body = request.read_body()
    if set(body) - {'project', 'language', 'projectRevision'}:
        raise studio.ApiError('project, language, projectRevision만 입력하세요.')
    reference, language, revision = body.get('project'), body.get('language'), body.get('projectRevision')
    if not isinstance(reference, str) or not reference or not isinstance(language, str):
        raise studio.ApiError('프로젝트와 생성 언어를 선택하세요.')
    studio.ensure_example_project_enabled(reference)
    store = studio.collaboration_store()
    current = store.get('projects', reference)
    if current is None:
        raise studio.ApiError('프로젝트를 찾을 수 없습니다.', status_code=404)
    if type(revision) is not int or revision < 1:
        raise studio.RevisionRequiredError(current.revision)
    if revision != current.revision:
        raise studio.RevisionConflictError(revision, current.revision)
    snapshot = snapshot_project(current.document, reference, revision, language, studio)
    manager = request.request.app.state.jobs
    def task(job):
        from api_test.request_scope import require_permission
        require_permission(studio, job.owner, 'run')
        return execute_snapshot(snapshot, studio, job.cancel)
    initial = {'kind': 'sdk_generation', 'generation': initial_metadata(snapshot)}
    return request.json_response(202, manager.submit(task, owner=store.context, projects=(reference,), initial=initial))


def download_artifact(request, studio, run_id):
    manager = request.request.app.state.jobs
    owner = studio.collaboration_store().context
    archive, filename, lease_id = manager.artifact(run_id, owner)
    try:
        return _ArtifactResponse(archive, filename, manager, lease_id)
    except BaseException:
        manager.release_artifact(lease_id)
        raise


def generate_client(request, studio):
    """Legacy ZIP endpoint uses the same bounded executor and shared worker slot."""
    body = request.read_body()
    reference, language = body.get('project'), body.get('language')
    if not isinstance(reference, str) or not reference or not isinstance(language, str):
        raise studio.ApiError('생성할 프로젝트와 언어를 선택하세요.')
    studio.ensure_example_project_enabled(reference)
    current = studio.collaboration_store().get('projects', reference)
    if current is None:
        raise studio.ApiError('선택한 프로젝트를 찾을 수 없습니다.')
    snapshot = snapshot_project(current.document, reference, current.revision, language, studio)
    with request.request.app.state.jobs.legacy_slot():
        result = execute_snapshot(snapshot, studio, threading.Event(), timeout_seconds=300)
    if result['status'] != 'passed':
        if result['status'] == 'timeout':
            raise studio.ApiError('OpenAPI 클라이언트 생성 시간이 300초를 초과했습니다.', status_code=504)
        raise studio.ApiError(result.get('error') or 'SDK 생성 작업을 완료하지 못했습니다.')
    return request.attachment_response(result['_artifact'], result['_artifact_filename'])
