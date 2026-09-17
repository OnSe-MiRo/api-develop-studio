"""Metadata edits that retain untouched OpenAPI references and extensions."""
from copy import deepcopy
import json
import posixpath
from urllib.parse import unquote


def edit_operation(project, payload, studio):
    action = payload.get('action')
    if action not in ('update', 'delete'):
        raise studio.ApiError('지원하지 않는 operation 편집 작업입니다.')
    method, path = payload.get('method'), payload.get('path')
    if not isinstance(method, str) or method.lower() not in studio.HTTP_METHODS or not isinstance(path, str):
        raise studio.ApiError('API method와 path를 확인하세요.')
    method = method.lower()
    updated = deepcopy(project)
    bundle = updated.get('docs_bundle')
    target_file = None
    if bundle is not None:
        entrypoint, files = studio.bundle_files(bundle)
        document = studio.parse_bundle_file(entrypoint, files[entrypoint])
    else:
        document = deepcopy(studio.project_openapi_document(project))
    if not str(document.get('openapi', '')).startswith('3.'):
        raise studio.ApiError('operation 편집은 OpenAPI 3.x 문서에서 지원합니다.')
    paths = document.get('paths', {})
    item = paths.get(path)
    if isinstance(item, dict) and '$ref' in item:
        ref = item['$ref']
        if bundle is None or not isinstance(ref, str) or '#' in ref or ':' in ref:
            raise studio.ApiError('이 path 참조 형식은 아직 편집할 수 없습니다.')
        target_file = studio.normalize_bundle_path(posixpath.join(posixpath.dirname(entrypoint), unquote(ref)))
        if sum(value == item for value in paths.values()) > 1:
            raise studio.ApiError('여러 path가 공유하는 참조는 직접 편집할 수 없습니다.')
        if target_file not in files:
            raise studio.ApiError('OpenAPI path 파일을 찾을 수 없습니다.')
        item = studio.parse_bundle_file(target_file, files[target_file])
    if not isinstance(item, dict) or not isinstance(item.get(method), dict):
        raise studio.ApiError('수정할 operation을 찾을 수 없습니다.')
    operation = item[method]
    if '$ref' in operation:
        raise studio.ApiError('참조 operation은 직접 편집할 수 없습니다.')
    if action == 'delete':
        del item[method]
    else:
        changes = payload.get('changes')
        if not isinstance(changes, dict) or not changes or set(changes) - {'operationId', 'summary', 'description', 'tags', 'deprecated'}:
            raise studio.ApiError('수정 가능한 operation 필드를 확인하세요.')
        for key, value in changes.items():
            valid = isinstance(value, bool) if key == 'deprecated' else (
                isinstance(value, list) and all(isinstance(tag, str) for tag in value)
                if key == 'tags' else isinstance(value, str)
            )
            if not valid or (key == 'operationId' and not value.strip()):
                raise studio.ApiError(f'operation {key} 값이 올바르지 않습니다.')
        operation.update(changes)
    if bundle is not None:
        filename = target_file or entrypoint
        content = item if target_file else document
        bundle['files'][filename] = (json.dumps(content, ensure_ascii=False, indent=2)
                                     if filename.endswith('.json') else studio.yaml_content(content))
        resolved = studio.resolve_openapi_bundle(bundle)
    else:
        updated['docs_url'] = ''
        updated['docs_file'] = {'name': 'openapi.json', 'document': document}
        resolved = document
    ids = set()
    for path_item in resolved.get('paths', {}).values():
        if not isinstance(path_item, dict):
            continue
        for verb in studio.HTTP_METHODS:
            op = path_item.get(verb)
            if isinstance(op, dict) and op.get('operationId'):
                identifier = op['operationId']
                if not isinstance(identifier, str) or identifier in ids:
                    raise studio.ApiError(f'중복되거나 잘못된 Operation ID입니다: {identifier}')
                ids.add(identifier)
    studio.openapi_document_operations(resolved)
    return updated, {} if action == 'delete' else operation
