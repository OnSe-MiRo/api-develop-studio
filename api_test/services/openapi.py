"""OpenAPI authoring, inspection and client generation services."""
from api_test.openapi_editing import edit_operation


def inspect_document(request, studio):
    body = request.read_body()
    document = body.get("document")
    bundle = body.get("bundle")
    url = body.get("url")
    no_proxy = body.get("no_proxy", False)
    for_case = body.get("for_case", False)
    if not isinstance(no_proxy, bool):
        raise studio.ApiError("API docs no_proxy must be true or false")
    if not isinstance(for_case, bool):
        raise studio.ApiError("API docs for_case must be true or false")
    source_count = int(document is not None) + int(bundle is not None) + int(isinstance(url, str) and bool(url.strip()))
    if source_count != 1:
        raise studio.ApiError("Use exactly one API docs URL, document, or bundle")
    if bundle is not None:
        operations = studio.openapi_document_operations(studio.resolve_openapi_bundle(bundle), for_case=for_case)
    elif document is not None:
        operations = studio.openapi_document_operations(document, for_case=for_case)
    else:
        operations = studio.load_openapi_document(url.strip(), no_proxy=no_proxy, for_case=for_case)
    from api_test.test_coverage import source_for
    if bundle is not None or document is not None:
        resolved = studio.resolve_openapi_bundle(bundle) if bundle is not None else document
        for operation in operations:
            operation['spec_source'] = source_for(operation, resolved)
    return request.json_response(200, {"operations": studio.normalize_openapi_value(operations)})


def author_operation(request, studio):
    reference = request.request.path_params["reference"]
    studio.ensure_example_project_enabled(reference)
    studio.ensure_example_document_writable("projects", reference)
    payload, expected_revision = studio.storage_request(request.read_body())
    store = studio.collaboration_store()
    current = store.get("projects", reference)
    if current is None:
        raise studio.ApiError("선택한 프로젝트를 찾을 수 없습니다.")
    if payload.get("action", "create") != "create":
        updated_project, operation = edit_operation(current.document, payload, studio)
        studio.validate_project_document(updated_project)
        stored = store.save("projects", reference, updated_project, expected_revision=expected_revision,
                            actor_id=request.actor_id(), action=f"{payload['action']}_openapi_operation")
        return request.json_response(200, {"operation": operation, "_storage": stored.metadata()})
    has_source = bool(current.document.get("docs_url")) or isinstance(current.document.get("docs_file"), dict) or isinstance(current.document.get("docs_bundle"), dict)
    source_document = studio.project_openapi_document(current.document) if has_source else None
    document, operation = studio.author_openapi_operation(current.document, payload, source_document)
    updated_project = {**current.document, "docs_url": "", "docs_bundle": studio.split_openapi_bundle(document)}
    updated_project.pop("docs_file", None)
    studio.validate_project_document(updated_project)
    stored = store.save(
        "projects", reference, updated_project, expected_revision=expected_revision,
        actor_id=request.actor_id(), action="author_openapi_operation",
    )
    return request.json_response(200, {"operation": operation, "_storage": stored.metadata()})


def generate_client(request, studio):
    body = request.read_body()
    project_reference = body.get("project")
    language = body.get("language")
    if not isinstance(project_reference, str) or not project_reference:
        raise studio.ApiError("생성할 프로젝트를 선택하세요.")
    if not isinstance(language, str):
        raise studio.ApiError("생성 언어를 선택하세요.")
    studio.ensure_example_project_enabled(project_reference)
    stored = studio.collaboration_store().get("projects", project_reference)
    if stored is None:
        raise studio.ApiError("선택한 프로젝트를 찾을 수 없습니다.")
    document = studio.project_openapi_document(stored.document)
    project_name = stored.document.get("name", project_reference.removesuffix(".json"))
    bundle = stored.document.get("docs_bundle")
    archive, filename = studio.generate_openapi_archive(
        document, language, project_name if isinstance(project_name, str) else project_reference,
        bundle if isinstance(bundle, dict) else None,
    )
    return request.attachment_response(archive, filename)



def check_contract(request, studio):
    from api_test.contracts import ContractError, project_document, lint, compare
    reference = request.request.path_params["reference"]
    studio.ensure_example_project_enabled(reference)
    body = request.read_body()
    store = studio.collaboration_store()
    current = store.get("projects", reference)
    if current is None:
        raise studio.ApiError("Project not found", status_code=404)
    try:
        document = project_document(current.document)
        baseline_revision = body.get("baselineRevision")
        if baseline_revision is None:
            issues = lint(document)
            result = {"issues": issues, "changes": [], "compatible": not any(item["severity"] == "error" for item in issues)}
        else:
            baseline = project_document(store.revision_document("projects", reference, baseline_revision))
            result = compare(baseline, document)
        return request.json_response(200, {**result, "currentRevision": current.revision, "baselineRevision": baseline_revision})
    except studio.DocumentNotFoundError as exc:
        raise studio.ApiError("Document revision not found", status_code=404) from exc
    except (ContractError, RecursionError) as exc:
        raise studio.ApiError("명세 검사 실패: " + (str(exc) if isinstance(exc, ContractError) else "문서 중첩 한도 초과")) from None


def test_coverage(request, studio):
    from api_test.test_coverage import linked_operation, source_for, sync_preview, apply_sync, response_key
    reference = request.request.path_params['reference']
    studio.ensure_example_project_enabled(reference)
    store = studio.collaboration_store()
    project = store.get('projects', reference)
    if project is None:
        raise studio.ApiError('프로젝트를 찾을 수 없습니다.', status_code=404)
    document = studio.project_openapi_document(project.document)
    operations = studio.openapi_document_operations(document, for_case=True)
    body = request.read_body()
    case_reference = body.get('case')
    if case_reference:
        current = store.get('cases', case_reference)
        if current is None or current.document.get('project') != reference:
            raise studio.ApiError('프로젝트 케이스를 찾을 수 없습니다.', status_code=404)
        operation = linked_operation(current.document, operations)
        if operation is None:
            raise studio.ApiError('연결된 operation이 삭제되었거나 연결이 모호합니다.')
        preview = sync_preview(current.document, operation, source_for(operation, document))
        if body.get('apply') is True:
            if type(body.get('caseRevision')) is not int or body['caseRevision'] != current.revision:
                raise studio.ApiError('케이스가 변경되었습니다. 미리보기를 다시 불러오세요.', status_code=409)
            studio.ensure_example_document_writable('cases', case_reference, current.document)
            if body.get('projectRevision') != project.revision:
                raise studio.ApiError('명세가 변경되었습니다. 미리보기를 다시 불러오세요.', status_code=409)
            try:
                updated = apply_sync(current.document, preview, body.get('fields', []))
            except ValueError as exc:
                raise studio.ApiError(str(exc)) from exc
            saved = store.save('cases', case_reference, updated, expected_revision=body.get('caseRevision'),
                               actor_id=request.actor_id(), action='sync_case_spec')
            return request.json_response(200, {'_storage': saved.metadata()})
        return request.json_response(200, {**preview, 'caseRevision': current.revision, 'projectRevision': project.revision})
    cases = [(ref, store.get('cases', ref)) for ref in store.list_references('cases', reference)]
    successes = studio.execution_history().case_successes(reference)
    rows, unlinked = [], []
    links = {}
    for ref, saved in cases:
        operation = linked_operation(saved.document, operations)
        if operation is None:
            unlinked.append(ref)
        else:
            links.setdefault(operation['id'], []).append((ref, saved.document))
    for operation in operations:
        linked = links.get(operation['id'], [])
        source = source_for(operation, document)
        responses = []
        for response in operation['responses']:
            status = str(response['status'])
            refs = [ref for ref, case in linked if response_key(case.get('expected', {}).get('status'), operation['responses']) == status]
            responses.append({'status': status, 'cases': refs, 'lastSuccess': max((stamp for (ref, actual), stamp in successes.items() if ref in refs and response_key(actual, operation['responses']) == status), default='') or None})
        rows.append({'id': operation['id'], 'responses': responses, 'lastSuccess': max((stamp for (ref, status), stamp in successes.items() if any(ref == linked_ref for linked_ref, _ in linked)), default='') or None, 'cases': [
            {'reference': ref, 'changed': case.get('spec_source', {}).get('fingerprint') != source['fingerprint'],
             'linked': bool(case.get('spec_source'))} for ref, case in linked]})
    return request.json_response(200, {'operations': rows, 'unlinked': unlinked})
