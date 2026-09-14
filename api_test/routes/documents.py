from __future__ import annotations

import json


def handle_get(request, parts: list[str], studio):
    store = studio.collaboration_store()
    if parts == ["api", "cases"]:
        references = store.list_references("cases", request.query_value("project"))
        return request.json_response(200, {"items": references, "details": studio.case_summaries(studio.CASE_ROOT, references)})
    elif parts == ["api", "pipelines"]:
        return request.json_response(200, {"items": store.list_references("pipelines", request.query_value("project"))})
    elif parts == ["api", "projects"]:
        references = store.list_references("projects")
        if not studio.example_project_enabled():
            references = [reference for reference in references if reference != studio.EXAMPLE_PROJECT_REFERENCE]
        return request.json_response(200, {"items": references, "details": studio.project_summaries(studio.PROJECT_ROOT, references)})
    elif len(parts) == 4 and parts[:2] == ["api", "cases"] and parts[3] == "revisions":
        return request.json_response(200, {"items": store.revisions("cases", parts[2])})
    elif len(parts) == 4 and parts[:2] == ["api", "pipelines"] and parts[3] == "revisions":
        return request.json_response(200, {"items": store.revisions("pipelines", parts[2])})
    elif len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "revisions":
        studio.ensure_example_project_enabled(parts[2])
        return request.json_response(200, {"items": store.revisions("projects", parts[2])})
    elif len(parts) == 3 and parts[:2] == ["api", "cases"]:
        stored = store.get("cases", parts[2])
        if stored is None:
            raise studio.DocumentNotFoundError("JSON file not found")
        document = studio.case_variables_for_client(stored.document)
        expected = document.get("expected", {})
        if isinstance(expected, dict) and "body" in expected:
            document["_expectedBodyRaw"] = json.dumps(expected["body"], ensure_ascii=False, indent=2)
        document["_storage"] = stored.metadata()
        return request.json_response(200, document)
    elif len(parts) == 3 and parts[:2] == ["api", "pipelines"]:
        stored = store.get("pipelines", parts[2])
        if stored is None:
            raise studio.DocumentNotFoundError("JSON file not found")
        return request.json_response(200, {**stored.document, "_storage": stored.metadata()})
    elif len(parts) == 3 and parts[:2] == ["api", "projects"]:
        studio.ensure_example_project_enabled(parts[2])
        stored = store.get("projects", parts[2])
        if stored is None:
            raise studio.DocumentNotFoundError("JSON file not found")
        visible = {"api_key": studio.EXAMPLE_API_KEY} if parts[2] == studio.EXAMPLE_PROJECT_REFERENCE else None
        project = studio.project_variables_for_client(stored.document, visible)
        return request.json_response(200, {**project, "_storage": stored.metadata()})
    else:
        return False


def handle_put(request, parts: list[str], studio):
    if len(parts) != 3 or parts[:2] not in (["api", "cases"], ["api", "pipelines"], ["api", "projects"]):
        return False
    payload, expected_revision = studio.storage_request(request.read_body())
    store = studio.collaboration_store()
    existing = None
    current = store.get(parts[1], parts[2])
    studio.ensure_example_document_writable(parts[1], parts[2], current.document if current else None, payload)
    if parts[:2] == ["api", "cases"]:
        kind = "cases"
        current = store.get(kind, parts[2])
        payload = studio.normalize_case_document(payload, current.document if current is not None else None)
        studio.validate_project_reference(payload)
    elif parts[:2] == ["api", "pipelines"]:
        kind = "pipelines"
        studio.validate_project_reference(payload)
    else:
        studio.ensure_example_project_enabled(parts[2])
        kind = "projects"
        current = store.get(kind, parts[2])
        existing = current.document if current is not None else None
        payload = studio.normalize_project_document(payload, existing)
        studio.validate_project_document(payload)
    stored = store.save(kind, parts[2], payload, expected_revision=expected_revision, actor_id=request.actor_id())
    if kind == "projects" and (existing is None or studio.fingerprint(existing) != studio.fingerprint(payload)):
        studio.OwnershipStore().revoke(parts[2])
    path = studio.safe_file({"cases": studio.CASE_ROOT, "pipelines": studio.PIPELINE_ROOT, "projects": studio.PROJECT_ROOT}[kind], parts[2])
    return request.json_response(200, {"path": path.relative_to(studio.ROOT).as_posix(), "_storage": stored.metadata()})


def handle_delete(request, parts: list[str], studio):
    if len(parts) != 3 or parts[0] != "api" or parts[1] not in {"cases", "pipelines", "projects"}:
        return False
    store = studio.collaboration_store()
    if parts[1] == "projects":
        studio.ensure_example_project_enabled(parts[2])
    current = store.get(parts[1], parts[2])
    studio.ensure_example_document_writable(parts[1], parts[2], current.document if current else None)
    deleted_pipelines: list[str] = []
    if parts[1] == "projects":
        if store.list_references("cases", parts[2]):
            raise studio.ApiError("Delete the project's API cases before deleting the project")
        deleted_pipelines = store.list_references("pipelines", parts[2])
        for pipeline_reference in deleted_pipelines:
            store.delete("pipelines", pipeline_reference, actor_id=request.actor_id())
    store.delete(parts[1], parts[2], actor_id=request.actor_id())
    if parts[1] == "projects":
        studio.OwnershipStore().revoke(parts[2], remove=True)
    root_name = {"cases": "case", "pipelines": "pipelines", "projects": "projects"}[parts[1]]
    return request.json_response(200, {"deleted": f"{root_name}/{parts[2]}", "deleted_pipelines": deleted_pipelines})
