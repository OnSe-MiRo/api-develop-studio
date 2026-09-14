"""Versioned document operations, independent of HTTP route dispatch."""
import json


def list_documents(request, studio, kind):
    store = studio.collaboration_store()
    references = store.list_references(kind, request.query_value('project') if kind != 'projects' else None)
    if kind == 'projects' and not studio.example_project_enabled():
        references = [item for item in references if item != studio.EXAMPLE_PROJECT_REFERENCE]
    result = {'items': references}
    if kind == 'projects':
        result['details'] = studio.project_summaries(studio.PROJECT_ROOT, references)
    elif kind == 'cases':
        result['details'] = studio.case_summaries(studio.CASE_ROOT, references)
    return request.json_response(200, result)


def list_revisions(request, studio, kind):
    reference = request.request.path_params['reference']
    if kind == 'projects':
        studio.ensure_example_project_enabled(reference)
    return request.json_response(200, {'items': studio.collaboration_store().revisions(kind, reference)})


def get_document(request, studio, kind):
    reference = request.request.path_params['reference']
    if kind == 'projects':
        studio.ensure_example_project_enabled(reference)
    stored = studio.collaboration_store().get(kind, reference)
    if stored is None:
        raise studio.DocumentNotFoundError('JSON file not found')
    document = dict(stored.document)
    if kind == 'projects':
        document = studio.profiles_for_client(document)
        if reference == studio.EXAMPLE_PROJECT_REFERENCE:
            document['variables'] = studio.project_variables_for_client(stored.document, {'api_key': studio.EXAMPLE_API_KEY})['variables']
    elif kind == 'cases':
        document = studio.case_variables_for_client(document)
        expected = document.get('expected', {})
        if isinstance(expected, dict) and 'body' in expected:
            document['_expectedBodyRaw'] = json.dumps(expected['body'], ensure_ascii=False, indent=2)
    return request.json_response(200, {**document, '_storage': stored.metadata()})


def save_document(request, studio, kind):
    reference = request.request.path_params['reference']
    payload, expected_revision = studio.storage_request(request.read_body())
    store = studio.collaboration_store()
    current = store.get(kind, reference)
    existing = current.document if current else None
    studio.ensure_example_document_writable(kind, reference, existing, payload)
    if kind == 'cases':
        payload = studio.normalize_case_document(payload, existing)
        studio.validate_project_reference(payload)
    elif kind == 'pipelines':
        studio.validate_project_reference(payload)
    else:
        studio.ensure_example_project_enabled(reference)
        payload = studio.normalize_project_document(payload, existing)
        studio.validate_project_document(payload)
    stored = store.save(kind, reference, payload, expected_revision=expected_revision, actor_id=request.actor_id())
    if kind == 'projects' and (existing is None or studio.fingerprint(existing) != studio.fingerprint(payload)):
        studio.OwnershipStore().revoke(reference)
    root = {'cases': studio.CASE_ROOT, 'pipelines': studio.PIPELINE_ROOT, 'projects': studio.PROJECT_ROOT}[kind]
    path = studio.safe_file(root, reference)
    return request.json_response(200, {'path': path.relative_to(studio.ROOT).as_posix(), '_storage': stored.metadata()})


def delete_document(request, studio, kind):
    reference = request.request.path_params['reference']
    store = studio.collaboration_store()
    if kind == 'projects':
        studio.ensure_example_project_enabled(reference)
    current = store.get(kind, reference)
    studio.ensure_example_document_writable(kind, reference, current.document if current else None)
    deleted_pipelines = []
    if kind == 'projects':
        if store.list_references('cases', reference):
            raise studio.ApiError("Delete the project's API cases before deleting the project")
        deleted_pipelines = store.list_references('pipelines', reference)
        for pipeline in deleted_pipelines:
            store.delete('pipelines', pipeline, actor_id=request.actor_id())
    store.delete(kind, reference, actor_id=request.actor_id())
    if kind == 'projects':
        studio.OwnershipStore().revoke(reference, remove=True)
    root = {'cases': 'case', 'pipelines': 'pipelines', 'projects': 'projects'}[kind]
    return request.json_response(200, {'deleted': f'{root}/{reference}', 'deleted_pipelines': deleted_pipelines})
