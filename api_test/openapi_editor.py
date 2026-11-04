"""Raw-owner OpenAPI 3.x editing; display resolvers never become saved source."""
from __future__ import annotations

from copy import deepcopy
import json
import math
import posixpath
import re
from urllib.parse import unquote

from api_test.contracts.documents import ContractError, bundle_document, digest, local_path, project_document
from api_test.contracts.validation import lint, operations
from api_test.contracts.documents import resolve

METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
MAX_EDITS = 100


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _parts(pointer: str) -> list[str]:
    if pointer == "#":
        return []
    if not isinstance(pointer, str) or not pointer.startswith("#/"):
        raise ValueError("JSON Pointer must start with #/")
    raw = unquote(pointer[2:]).split("/")
    if any(re.search(r"~(?![01])", part) for part in raw):
        raise ValueError("Invalid JSON Pointer escape")
    return [part.replace("~1", "/").replace("~0", "~") for part in raw]


def _json_clone(value, stack=None):
    """Break YAML aliases before a targeted edit; reject lossy non-JSON values."""
    stack = set() if stack is None else stack
    if isinstance(value, (dict, list)):
        if id(value) in stack:
            raise ValueError("Recursive YAML aliases cannot be edited")
        stack.add(id(value))
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise ValueError("Non-string YAML keys cannot be edited")
            copy = {key: _json_clone(child, stack) for key, child in value.items()}
        else:
            copy = [_json_clone(child, stack) for child in value]
        stack.remove(id(value))
        return copy
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError("Non-JSON YAML scalars cannot be edited")


def _array_index(segment: str) -> int:
    if not re.fullmatch(r"0|[1-9][0-9]*", segment):
        raise KeyError(segment)
    return int(segment)


def _get(value, pointer: str):
    current = value
    for part in _parts(pointer):
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list):
            current = current[_array_index(part)]
        else:
            raise KeyError(pointer)
    return current


def _raw_source(project, studio):
    bundle = project.get("docs_bundle")
    if bundle is not None:
        entry, raw = studio.bundle_files(bundle)
        try:
            parsed = {name: _json_clone(studio.parse_bundle_file(name, content)) for name, content in raw.items()}
        except (ValueError, RecursionError) as exc:
            raise studio.ApiError("OpenAPI bundle에 JSON으로 표현할 수 없는 YAML 값 또는 순환 alias가 있습니다.") from exc
        return {"kind": "bundle", "entrypoint": entry, "files": parsed, "rawFiles": raw}
    doc = project.get("docs_file")
    if isinstance(doc, dict) and isinstance(doc.get("document"), dict):
        name = doc.get("name") or "openapi.json"
        name = studio.normalize_bundle_path(name)
        return {"kind": "file", "entrypoint": name, "files": {name: _json_clone(doc["document"])}, "rawFiles": {}}
    url = project.get("docs_url")
    if isinstance(url, str) and url.strip():
        advanced = project.get("advanced", {})
        use_proxy = advanced.get("use_proxy", True) if isinstance(advanced, dict) else True
        document = studio.fetch_openapi_document(url.strip(), no_proxy=use_proxy is False)
        name = "openapi.json"
        try:
            document = _json_clone(document)
        except (ValueError, RecursionError) as exc:
            raise studio.ApiError("원격 OpenAPI 문서에 JSON으로 표현할 수 없는 YAML 값이 있습니다.") from exc
        return {"kind": "file", "entrypoint": name, "files": {name: document}, "rawFiles": {},
                "origin": {"kind": "url", "url": url.strip()}}
    title = project.get("name") if isinstance(project.get("name"), str) and project["name"].strip() else "API"
    name = "openapi.json"
    draft = {"openapi": "3.0.3", "info": {"title": title, "version": "1.0.0"}, "paths": {}}
    return {"kind": "file", "entrypoint": name, "files": {name: draft}, "rawFiles": {},
            "origin": {"kind": "draft"}}


def _source_digest(source):
    content = source["rawFiles"] if source["kind"] == "bundle" else source["files"]
    return digest({"kind": source["kind"], "entrypoint": source["entrypoint"], "content": content})


def _normalize_import(source, studio):
    if not isinstance(source, dict) or source.get("kind") not in ("bundle", "file"):
        raise studio.ApiError("source.kind는 bundle 또는 file이어야 합니다.")
    entry = source.get("entrypoint")
    entry = studio.normalize_bundle_path(entry)
    raw = source.get("rawFiles")
    files = source.get("files")
    if source["kind"] == "bundle":
        if not isinstance(raw, dict) or not raw:
            if not isinstance(files, dict) or not files:
                raise studio.ApiError("bundle source.rawFiles가 필요합니다.")
            raw = {name: json.dumps(value, ensure_ascii=False, indent=2) if name.endswith(".json") else studio.yaml_content(value) for name, value in files.items()}
        _, raw = studio.bundle_files({"entrypoint": entry, "files": raw})
        try:
            parsed = {name: _json_clone(studio.parse_bundle_file(name, value)) for name, value in raw.items()}
        except (ValueError, RecursionError) as exc:
            raise studio.ApiError("OpenAPI bundle에 JSON으로 표현할 수 없는 YAML 값이 있습니다.") from exc
        if isinstance(files, dict) and files and parsed != files:
            raise studio.ApiError("source.files와 source.rawFiles 내용이 다릅니다.")
        return {"kind": "bundle", "entrypoint": entry, "files": parsed, "rawFiles": raw}
    if not isinstance(files, dict) or entry not in files:
        if not isinstance(raw, dict) or entry not in raw:
            raise studio.ApiError("file source.files 또는 rawFiles가 필요합니다.")
        files = {entry: studio.parse_bundle_file(entry, raw[entry])}
    if set(files) != {entry} or not isinstance(files[entry], dict):
        raise studio.ApiError("file source는 하나의 OpenAPI 객체여야 합니다.")
    if isinstance(raw, dict) and raw and studio.parse_bundle_file(entry, raw.get(entry, "")) != files[entry]:
        raise studio.ApiError("source.files와 source.rawFiles 내용이 다릅니다.")
    try:
        parsed_file = _json_clone(files[entry])
    except (ValueError, RecursionError) as exc:
        raise studio.ApiError("OpenAPI 파일에 JSON으로 표현할 수 없는 값이 있습니다.") from exc
    return {"kind": "file", "entrypoint": entry, "files": {entry: parsed_file}, "rawFiles": {}}


def _owner(source, value, filename, pointer, *, path_item=False):
    """Follow reference-only wrappers while keeping schema reference siblings in place."""
    seen = set()
    while isinstance(value, dict) and (set(value) == {"$ref"} or
                                     path_item and "$ref" in value and set(value) <= {"$ref", "summary", "description"}):
        reference = value["$ref"]
        if not isinstance(reference, str):
            break
        try:
            target_file, fragment = local_path(filename, reference)
            target_pointer = "#" + fragment if fragment else "#"
            key = (target_file, target_pointer)
            if key in seen:
                break
            seen.add(key)
            value = _get(source["files"][target_file], target_pointer)
            filename, pointer = key
        except (ContractError, KeyError, IndexError, TypeError, ValueError):
            break
    return filename, pointer, value


def _catalog(source):
    entry = source["entrypoint"]
    root = source["files"][entry]
    if not isinstance(root, dict):
        return {"schemas": [], "securitySchemes": [], "operations": [], "references": []}
    files = source["files"]
    schemas, security, operations, references = [], [], [], []
    components = root.get("components")
    components = components if isinstance(components, dict) else {}
    paths = root.get("paths")
    if isinstance(paths, dict):
        for path, raw_item in paths.items():
            if not isinstance(path, str):
                continue
            path_ptr = "#/paths/" + _escape(path)
            owner_file, owner_ptr, item = _owner(source, raw_item, entry, path_ptr, path_item=True)
            if not isinstance(item, dict):
                continue
            for method in METHODS:
                raw_operation = item.get(method)
                if isinstance(raw_operation, dict):
                    pointer = owner_ptr + "/" + method
                    operations.append({"path": path, "method": method.upper(), "file": owner_file, "pointer": pointer,
                                       "operationId": raw_operation.get("operationId")})
    for section, target in (("schemas", schemas), ("securitySchemes", security)):
        values = components.get(section)
        if not isinstance(values, dict):
            continue
        for name, raw_value in values.items():
            if not isinstance(name, str):
                continue
            pointer = "#/components/" + section + "/" + _escape(name)
            owner_file, owner_ptr, owned = _owner(source, raw_value, entry, pointer)
            item = {"name": name, "file": owner_file, "pointer": owner_ptr,
                    "entrypointPointer": pointer}
            if section == "schemas":
                item["refByFile"] = {name_: ((posixpath.relpath(entry, posixpath.dirname(name_) or ".") if name_ != entry else "") + pointer)
                                     for name_ in sorted(files)}
            target.append(item)
    def scan(value, filename, pointer):
        if isinstance(value, dict):
            ref = value.get("$ref")
            if isinstance(ref, str):
                item = {"file": filename, "pointer": pointer, "ref": ref}
                try:
                    file_, fragment = local_path(filename, ref)
                    item.update(targetFile=file_, targetPointer="#" + fragment if fragment else "#")
                except ContractError:
                    item["unsupported"] = True
                references.append(item)
            for key, child in value.items():
                scan(child, filename, pointer + "/" + _escape(str(key)))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                scan(child, filename, pointer + "/" + str(index))
    for filename, parsed in files.items():
        scan(parsed, filename, "#")
    return {"schemas": schemas, "securitySchemes": security, "operations": operations, "references": references,
            "documentSecurity": deepcopy(root.get("security"))}


def _patch(document, edit, entrypoint, filename):
    if not isinstance(edit, dict) or edit.get("op") not in ("add", "replace", "remove") or not isinstance(edit.get("path"), str):
        raise ValueError("Each edit needs op and JSON Pointer path")
    parts = _parts(edit["path"])
    if not parts:
        if edit["op"] != "replace" or filename == entrypoint and not isinstance(edit.get("value"), dict):
            raise ValueError("Entrypoint root must remain an OpenAPI object")
        return _json_clone(edit["value"])
    if edit["op"] != "remove" and "value" not in edit:
        raise ValueError("add/replace requires value")
    if filename == entrypoint and edit["op"] == "add" and len(parts) == 3 and parts[:2] in (["components", "schemas"], ["components", "securitySchemes"]):
        if not isinstance(document, dict):
            raise ValueError("OpenAPI owner root must be an object")
        components = document.setdefault("components", {})
        if not isinstance(components, dict):
            raise ValueError("components must be an object")
        section = components.setdefault(parts[1], {})
        if not isinstance(section, dict):
            raise ValueError("components section must be an object")
    current = document
    for segment in parts[:-1]:
        if isinstance(current, dict):
            current = current[segment]
        elif isinstance(current, list):
            current = current[_array_index(segment)]
        else:
            raise KeyError(edit["path"])
    last = parts[-1]
    if isinstance(current, dict):
        if edit["op"] == "add":
            if last in current:
                raise ValueError("add target already exists")
            current[last] = _json_clone(edit["value"])
        elif edit["op"] == "replace":
            if last not in current:
                raise KeyError(edit["path"])
            current[last] = _json_clone(edit["value"])
        else:
            del current[last]
    elif isinstance(current, list):
        if edit["op"] == "add" and last == "-":
            current.append(_json_clone(edit["value"]))
        elif re.fullmatch(r"0|[1-9][0-9]*", last) and 0 <= int(last) < len(current):
            index = int(last)
            if edit["op"] == "add":
                current.insert(index, _json_clone(edit["value"]))
            elif edit["op"] == "replace":
                current[index] = deepcopy(edit["value"])
            else:
                del current[index]
        else:
            raise KeyError(edit["path"])
    else:
        raise KeyError(edit["path"])
    return document


def _edited_source(current, payload, studio):
    replacement = payload.get("source")
    edits = payload.get("edits")
    if (replacement is None) == (edits is None):
        raise studio.ApiError("source 교체 또는 edits 중 하나만 보내세요.")
    if replacement is not None:
        return _normalize_import(replacement, studio)
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_EDITS:
        raise studio.ApiError(f"edits는 1~{MAX_EDITS}개여야 합니다.")
    source = deepcopy(current)
    changed = set()
    for edit in edits:
        filename = edit.get("file") if isinstance(edit, dict) else None
        if not isinstance(filename, str) or filename not in source["files"]:
            raise studio.ApiError("기존 원본 파일을 선택하세요.")
        try:
            if filename not in changed:
                source["files"][filename] = _json_clone(source["files"][filename])
            source["files"][filename] = _patch(source["files"][filename], edit, source["entrypoint"], filename)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise studio.ApiError("JSON Pointer 편집 대상 또는 값이 올바르지 않습니다.") from exc
        changed.add(filename)
    if source["kind"] == "bundle":
        for filename in changed:
            value = source["files"][filename]
            source["rawFiles"][filename] = (json.dumps(value, ensure_ascii=False, indent=2) if filename.endswith(".json")
                                            else studio.yaml_content(value))
    return source


def _project_with_source(project, source):
    updated = deepcopy(project)
    updated["docs_url"] = ""
    if source["kind"] == "bundle":
        updated["docs_bundle"] = {"entrypoint": source["entrypoint"], "files": source["rawFiles"]}
        updated.pop("docs_file", None)
    else:
        updated["docs_file"] = {"name": source["entrypoint"], "document": source["files"][source["entrypoint"]]}
        updated.pop("docs_bundle", None)
    return updated


def _security_issues(document):
    issues = []
    schemes = (document.get("components") or {}).get("securitySchemes") or {}
    if not isinstance(schemes, dict):
        return issues
    def check(requirements, location):
        if not isinstance(requirements, list):
            return
        for index, requirement in enumerate(requirements):
            if not isinstance(requirement, dict):
                continue
            for name, scopes in requirement.items():
                target = location + "/" + str(index) + "/" + _escape(str(name))
                if name not in schemes:
                    issues.append({"code": "unknown_security_scheme", "path": target, "severity": "error", "message": "선언하지 않은 security scheme입니다."})
                    continue
                try:
                    scheme = resolve(document, schemes[name])
                except ContractError:
                    continue
                if not isinstance(scheme, dict) or not isinstance(scopes, list):
                    continue
                if scheme.get("type") == "oauth2":
                    flows = scheme.get("flows") or {}
                    declared = {scope for flow in flows.values() if isinstance(flow, dict)
                                for scope in (flow.get("scopes") or {})}
                    if any(scope not in declared for scope in scopes):
                        issues.append({"code": "unknown_oauth_scope", "path": target, "severity": "error", "message": "선언하지 않은 OAuth scope입니다."})
                elif document["openapi"].startswith("3.0.") and scheme.get("type") in ("apiKey", "http") and scopes:
                    issues.append({"code": "unexpected_security_scope", "path": target, "severity": "error", "message": "이 security scheme은 scope를 사용하지 않습니다."})
    check(document.get("security"), "#/security")
    seen = set()
    for path, method, operation, _ in operations(document):
        identifier = operation.get("operationId")
        location = "#/paths/" + _escape(path) + "/" + method
        if isinstance(identifier, str) and identifier:
            if identifier in seen:
                issues.append({"code": "duplicate_operation_id", "path": location + "/operationId", "severity": "error", "message": "중복 operationId입니다."})
            seen.add(identifier)
        check(operation.get("security", document.get("security")), location + "/security")
    return issues


def _issues(project, source, studio):
    try:
        document = bundle_document(project["docs_bundle"]) if source["kind"] == "bundle" else project_document(project)
        issues = lint(document)
        if not any(item["severity"] == "error" for item in issues):
            issues.extend(_security_issues(document))
        if not any(item["severity"] == "error" for item in issues):
            studio.validate_project_document(project)
        return issues
    except (ContractError, studio.ApiError, ValueError):
        return [{"code": "invalid_document_or_reference", "path": "#", "severity": "error",
                 "message": "OpenAPI 구조 또는 로컬 참조를 확인하세요."}]


def _changed_files(before, after):
    old = before["rawFiles"] if before["kind"] == "bundle" else before["files"]
    new = after["rawFiles"] if after["kind"] == "bundle" else after["files"]
    if before["kind"] != after["kind"] or before["entrypoint"] != after["entrypoint"]:
        return sorted(set(old) | set(new))
    return sorted(name for name in set(old) | set(new) if old.get(name) != new.get(name))


def _affected(before, after, changed):
    old, new = _catalog(before), _catalog(after)
    operations = old["operations"] + new["operations"]
    owner_files = {item["file"] for item in operations}
    component_files = {item["file"] for catalog in (old, new)
                       for section in ("schemas", "securitySchemes") for item in catalog[section]}
    shared = any(name in {before["entrypoint"], after["entrypoint"]} or name in component_files or name not in owner_files
                 for name in changed)
    affected = {}
    for operation in operations:
        if shared or operation["file"] in changed:
            key = (operation["method"], operation["path"])
            affected[key] = {"method": operation["method"], "path": operation["path"], "operationId": operation.get("operationId")}
    return [affected[key] for key in sorted(affected)], "conservative_shared_source" if shared else "owner_file"


def inspect(project, metadata, studio):
    source = _raw_source(project, studio)
    return {"source": source, "catalog": _catalog(source), "sourceDigest": _source_digest(source), "_storage": metadata}


def preview(project, metadata, payload, studio):
    current = _raw_source(project, studio)
    if not isinstance(payload.get("sourceDigest"), str) or not re.fullmatch(r"[0-9a-f]{64}", payload["sourceDigest"]):
        raise studio.ApiError("64자리 sourceDigest가 필요합니다.")
    if payload["sourceDigest"] != _source_digest(current):
        raise studio.ApiError("OpenAPI 원본이 변경되었습니다. 다시 불러오세요.", status_code=409)
    source = _edited_source(current, payload, studio)
    updated = _project_with_source(project, source)
    issues = _issues(updated, source, studio)
    changed = _changed_files(current, source)
    affected, impact_scope = _affected(current, source, changed)
    return updated, {"valid": not any(item["severity"] == "error" for item in issues), "issues": issues,
                     "changedFiles": changed, "affectedOperations": affected, "impactScope": impact_scope,
                     "source": source, "sourceDigest": _source_digest(current), "nextSourceDigest": _source_digest(source),
                     "_storage": metadata}
