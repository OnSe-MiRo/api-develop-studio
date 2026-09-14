"""Ownership policy remains in the existing service/store implementation."""
def get_ownership(request, studio):
    request.ownership_session(create=True)
    project = request.query_value('project')
    stored = studio.collaboration_store().get('projects', project or '')
    if not stored:
        raise studio.OwnershipError('저장된 프로젝트를 선택하세요.')
    return request.json_response(200, studio.OwnershipStore().status(project, stored.document))


def perform_action(request, studio):
    return request.ownership_action(request.api_path())
