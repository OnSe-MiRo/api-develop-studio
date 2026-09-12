from __future__ import annotations


def handle_post(handler, parts: list[str], studio) -> bool:
    if parts == ["api", "docs"]:
        body = handler.read_body()
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
        handler.send_json(200, {"operations": studio.normalize_openapi_value(operations)})
        return True

    if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3:] == ["openapi", "operations"]:
        studio.ensure_example_project_enabled(parts[2])
        payload, expected_revision = studio.storage_request(handler.read_body())
        store = studio.collaboration_store()
        current = store.get("projects", parts[2])
        if current is None:
            raise studio.ApiError("선택한 프로젝트를 찾을 수 없습니다.")
        has_source = bool(current.document.get("docs_url")) or isinstance(current.document.get("docs_file"), dict) or isinstance(current.document.get("docs_bundle"), dict)
        source_document = studio.project_openapi_document(current.document) if has_source else None
        document, operation = studio.author_openapi_operation(current.document, payload, source_document)
        updated_project = {**current.document, "docs_url": "", "docs_bundle": studio.split_openapi_bundle(document)}
        updated_project.pop("docs_file", None)
        studio.validate_project_document(updated_project)
        stored = store.save(
            "projects", parts[2], updated_project, expected_revision=expected_revision,
            actor_id=handler.actor_id(), action="author_openapi_operation",
        )
        handler.send_json(200, {"operation": operation, "_storage": stored.metadata()})
        return True

    if parts == ["api", "generate"]:
        body = handler.read_body()
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
        handler.send_attachment(archive, filename)
        return True
    return False
