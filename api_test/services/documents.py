"""Versioned document operations, independent of HTTP route dispatch."""
import json


def list_documents(request, studio, kind):
    store = studio.collaboration_store()
    if kind == 'projects' and any(name in request.request.query_params for name in ('page_size', 'q', 'sort', 'cursor')):
        from api_test.project_listing import list_project_page
        try:
            result = list_project_page(store, page_size=request.query_value('page_size') or '20',
                                       search=request.query_value('q') or '', sort=request.query_value('sort') or 'reference_asc',
                                       cursor=request.query_value('cursor') or '', include_example=studio.example_project_enabled())
        except ValueError as error:
            raise studio.ApiError(str(error)) from error
        return request.json_response(200, result)
    references = store.list_references(kind, request.query_value('project') if kind != 'projects' else None)
    if kind == 'projects' and not studio.example_project_enabled():
        references = [item for item in references if item != studio.EXAMPLE_PROJECT_REFERENCE]
    result = {'items': references}
    if kind == 'projects':
        result['details'] = studio.project_summaries(studio.document_root("projects"), references)
    elif kind == 'cases':
        result['details'] = studio.case_summaries(studio.document_root("cases"), references)
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
        studio.OwnershipStore(context=studio.current_context()).revoke(reference)
    root = {'cases': studio.document_root("cases"), 'pipelines': studio.document_root("pipelines"), 'projects': studio.document_root("projects")}[kind]
    path = studio.safe_file(root, reference)
    prefix = {'cases': 'case', 'pipelines': 'pipelines', 'projects': 'projects'}[kind]
    return request.json_response(200, {'path': f'{prefix}/{reference}', '_storage': stored.metadata()})


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
        studio.OwnershipStore(context=studio.current_context()).revoke(reference, remove=True)
    root = {'cases': 'case', 'pipelines': 'pipelines', 'projects': 'projects'}[kind]
    return request.json_response(200, {'deleted': f'{root}/{reference}', 'deleted_pipelines': deleted_pipelines})
