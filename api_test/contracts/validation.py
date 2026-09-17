"""Standard OpenAPI lint and value-free response diagnostics."""
import re
import math
from urllib.parse import urlsplit
from itertools import islice
from openapi_spec_validator import OpenAPIV30SpecValidator, OpenAPIV31SpecValidator
from openapi_schema_validator import OAS30ReadValidator, OAS31Validator
from jsonschema import ValidationError
from jsonschema.validators import extend
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from .documents import ContractError, escape, pointer, resolve, walk

METHODS = ('get', 'put', 'post', 'delete', 'options', 'head', 'patch', 'trace')


def issue(code, path, severity='error', message=None):
    return {'code': code, 'path': path, 'severity': severity, 'message': message or code}


def operations(document):
    for path, item in document.get('paths', {}).items():
        if path.startswith('x-'):
            continue
        item = resolve(document, item)
        if isinstance(item, dict):
            for method in METHODS:
                if method in item:
                    yield path, method, resolve(document, item[method]), item


def lint(document):
    if not isinstance(document, dict) or not isinstance(document.get('openapi'), str) or not document['openapi'].startswith(('3.0.', '3.1.')):
        return [issue('unsupported_version', '#', message='OpenAPI 3.0/3.1 문서가 필요합니다.')]
    issues = []
    allowed_dialects = {'https://spec.openapis.org/oas/3.1/dialect/base', 'https://json-schema.org/draft/2020-12/schema'}
    dialect = document.get('jsonSchemaDialect', 'https://spec.openapis.org/oas/3.1/dialect/base')
    if not isinstance(dialect, str) or dialect not in allowed_dialects:
        issues.append(issue('unsupported_schema_dialect', '#/jsonSchemaDialect'))
    # Preflight before the standard validator: no network/file lookups, including unused components.
    for path, value in walk(document):
        if not isinstance(value, dict):
            continue
        if '$schema' in value and (not isinstance(value['$schema'], str) or value['$schema'] not in allowed_dialects):
            issues.append(issue('unsupported_schema_dialect', path))
        if '$ref' in value and len(set(value) - {'$ref', 'description', 'summary'}) > 0:
            issues.append(issue('unsupported_ref_siblings', path))
        for keyword in ('$id', '$dynamicRef', '$dynamicAnchor', '$anchor'):
            if keyword in value:
                issues.append(issue('unsupported_reference_scope', path + '/' + keyword))
        if '$ref' in value:
            try:
                pointer(document, value['$ref'])
            except ContractError:
                issues.append(issue('unresolved_or_external_ref', path + '/$ref'))
    if issues:
        return issues[:100]
    cls = OpenAPIV30SpecValidator if document['openapi'].startswith('3.0.') else OpenAPIV31SpecValidator
    try:
        for error in islice(cls(document).iter_errors(), 100):
            location = '#/' + '/'.join(escape(part) for part in getattr(error, 'absolute_path', []))
            # Validator messages can echo example/enum data. Return only rule and location.
            issues.append(issue('invalid_structure', location, message=f'OpenAPI 구조 오류 ({getattr(error, "validator", None) or "constraint"})'))
    except (ValueError, TypeError, KeyError, RecursionError):
        issues.append(issue('invalid_structure', '#', message='OpenAPI 구조 또는 참조를 검사할 수 없습니다.'))
    if issues:
        return issues
    for path, method, operation, _ in operations(document):
        location = '#/paths/' + escape(path) + '/' + method
        for key in ('operationId', 'summary'):
            if not operation.get(key):
                issues.append(issue('missing_' + key, location, 'warning'))
    return issues[:100]


def schema_errors(document, schema, value, location):
    cls = OAS30ReadValidator if document['openapi'].startswith('3.0.') else OAS31Validator
    def read_required(validator, required, instance, current_schema):
        if not validator.is_type(instance, 'object'):
            return
        for name in required:
            prop = resolve(document, current_schema.get('properties', {}).get(name, {}))
            if name not in instance and not (isinstance(prop, dict) and prop.get('writeOnly')):
                yield ValidationError('Required response property is missing')
    cls = extend(cls, {'required': read_required})
    registry = Registry().with_resource('urn:studio:contract', Resource(document, DRAFT202012))
    validator = cls(schema, registry=registry, _resolver=registry.resolver('urn:studio:contract'), format_checker=cls.FORMAT_CHECKER)
    errors = []
    try:
        for error in islice(validator.iter_errors(value), 100):
            # No actual/expected values, schema values, or raw messages in diagnostics.
            errors.append(issue('schema_' + str(error.validator), location + '/' + '/'.join(escape(part) for part in error.absolute_path)))
    except (ValueError, TypeError, KeyError, RecursionError):
        errors.append(issue('schema_validation_error', location))
    return errors


def match_operation(document, method, url, base_url=None):
    path = urlsplit(url).path or '/'
    candidates = {path}
    servers = [base_url] if base_url else []
    servers.extend(server.get('url', '') for server in document.get('servers', []))
    for server in servers:
        prefix = urlsplit(server).path.rstrip('/')
        if prefix and (path == prefix or path.startswith(prefix + '/')):
            candidates.add(path[len(prefix):] or '/')
    matches = []
    for template, verb, operation, _ in operations(document):
        if verb != method.lower():
            continue
        pattern = '^' + re.sub(r'\\\{[^}]+\\\}', '[^/]+', re.escape(template)) + '$'
        if any(re.fullmatch(pattern, candidate) for candidate in candidates):
            matches.append((template.count('{'), template, operation))
    if not matches:
        raise ContractError('No matching OpenAPI operation')
    matches.sort(key=lambda item: item[0])
    if len(matches) > 1 and matches[0][0] == matches[1][0]:
        raise ContractError('Ambiguous OpenAPI operation')
    return matches[0][1:]


def validate_response(document, method, url, status, headers, body, *, raw_body=None, base_url=None):
    errors = [item for item in lint(document) if item['severity'] == 'error']
    if errors:
        return {'valid': False, 'issues': errors}
    try:
        path, operation = match_operation(document, method, url, base_url)
        responses = operation['responses']
        response = responses.get(str(status), responses.get(str(status)[0] + 'XX', responses.get('default')))
        if response is None:
            return {'valid': False, 'issues': [issue('undocumented_status', '#/response/status')]}
        response = resolve(document, response)
        normalized = {key.lower(): value for key, value in headers.items()}
        for name, header in response.get('headers', {}).items():
            if name.lower() == 'content-type':
                continue
            header = resolve(document, header)
            location = '#/response/headers/' + escape(name)
            if name.lower() not in normalized:
                if header.get('required'):
                    errors.append(issue('missing_header', location))
                continue
            if 'schema' not in header:
                errors.append(issue('unsupported_header_content', location))
                continue
            schema = resolve(document, header['schema'])
            value = normalized[name.lower()]
            schema_type = schema.get('type') if isinstance(schema, dict) else None
            try:
                if schema_type == 'integer':
                    value = int(value)
                elif schema_type == 'number':
                    number = float(value)
                    value = number if math.isfinite(number) else value
                elif schema_type == 'boolean' and value in ('true', 'false'):
                    value = value == 'true'
                elif schema_type == 'array':
                    errors.append(issue('unsupported_header_serialization', location))
                    continue
            except ValueError:
                pass
            errors.extend(schema_errors(document, header['schema'], value, location))
        if method.upper() == 'HEAD' or status in (204, 304):
            if raw_body not in (None, ''):
                errors.append(issue('unexpected_body', '#/response/body'))
            return {'valid': not errors, 'operation': method.upper() + ' ' + path, 'issues': errors[:100]}
        content = response.get('content', {})
        if not content:
            if raw_body not in (None, '') or (raw_body is None and body is not None):
                errors.append(issue('unexpected_body', '#/response/body'))
        else:
            media = normalized.get('content-type', '').split(';', 1)[0].strip().lower()
            media_schema = content.get(media, content.get(media.split('/')[0] + '/*', content.get('*/*')))
            if media_schema is None:
                errors.append(issue('undocumented_content_type', '#/response/content-type'))
            elif 'schema' in media_schema:
                if raw_body is not None and (media == 'application/json' or media.endswith('+json')):
                    import json
                    try:
                        body = json.loads(raw_body)
                    except (ValueError, TypeError):
                        errors.append(issue('invalid_json', '#/response/body'))
                        return {'valid': False, 'issues': errors}
                errors.extend(schema_errors(document, media_schema['schema'], body, '#/response/body'))
        return {'valid': not errors, 'operation': method.upper() + ' ' + path, 'issues': errors[:100]}
    except ContractError:
        return {'valid': False, 'issues': [issue('operation_or_reference_error', '#/response')]}
