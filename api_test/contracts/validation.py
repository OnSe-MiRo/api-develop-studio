"""Standard OpenAPI lint and value-free response diagnostics."""
import re
import json
import math
from urllib.parse import urlsplit, urljoin
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
        if '$ref' in value and not document['openapi'].startswith('3.1.') and len(set(value) - {'$ref', 'description', 'summary'}) > 0:
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
            raw_prop = current_schema.get('properties', {}).get(name, {})
            prop = resolve(document, raw_prop)
            sibling_write_only = False
            if document['openapi'].startswith('3.1.'):
                seen_refs = set()
                wrapper = raw_prop
                while isinstance(wrapper, dict):
                    sibling_write_only |= wrapper.get('writeOnly') is True
                    reference = wrapper.get('$ref')
                    if not isinstance(reference, str) or reference in seen_refs:
                        break
                    seen_refs.add(reference)
                    wrapper = pointer(document, reference)
            if name not in instance and not (isinstance(prop, dict) and prop.get('writeOnly')) and not sibling_write_only:
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


def validate_server_variables(value):
    """Validate explicit values without echoing names or values in diagnostics."""
    if not isinstance(value, dict) or len(value) > 32:
        raise ContractError('Server variables must be a string map with at most 32 entries')
    if any(not isinstance(key, str) or not 1 <= len(key) <= 128 or
           not isinstance(item, str) or len(item) > 512 or
           any(ord(char) < 32 for char in key + item) for key, item in value.items()):
        raise ContractError('Invalid server variable shape')
    return value


def validate_document_url(value):
    """A location hint only; never fetch it or include it in diagnostics."""
    if not isinstance(value, str) or not 1 <= len(value) <= 2048 or any(char.isspace() or ord(char) < 32 for char in value):
        raise ContractError('Invalid OpenAPI document location')
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment or '\\' in value:
            raise ContractError('Invalid OpenAPI document location')
        parsed.port
    except ValueError as error:
        raise ContractError('Invalid OpenAPI document location') from error
    return value


def _server_prefix(server, server_variables=None, document_url=None):
    """Expand declared values/defaults; no URL retrieval or implicit source location."""
    if not isinstance(server, dict) or not isinstance(server.get('url'), str):
        raise ContractError('Invalid server definition')
    variables = server.get('variables', {})
    supplied = server_variables or {}
    used = set(re.findall(r'\{([^{}]+)\}', server['url']))
    if any(key not in used for key in supplied):
        raise ContractError('Server variable is not used by this server')
    def substitute(match):
        variable = variables.get(match.group(1)) if isinstance(variables, dict) else None
        if not isinstance(variable, dict) or not isinstance(variable.get('default'), str):
            raise ContractError('Server variable default is required')
        default = supplied.get(match.group(1), variable['default'])
        if 'enum' in variable and default not in variable['enum']:
            raise ContractError('Invalid server variable default')
        return default
    expanded = re.sub(r'\{([^{}]+)\}', substitute, server['url'])
    if '{' in expanded or '}' in expanded or any(ord(char) < 32 for char in expanded):
        raise ContractError('Invalid server URL')
    try:
        # Resolve after variable substitution; the document URL is not the API base URL.
        if document_url is not None:
            expanded = urljoin(document_url, expanded)
        parsed = urlsplit(expanded)
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ContractError('Unsupported server URL')
        if parsed.scheme:
            if parsed.scheme not in ('http', 'https') or not parsed.hostname:
                raise ContractError('Unsupported server URL')
            parsed.port  # Validate malformed ports without exposing the source URL.
        elif not expanded.startswith('/'):
            raise ContractError('Server document location is required')
    except ValueError as error:
        raise ContractError('Invalid server URL') from error
    return parsed.path.rstrip('/')


def match_operation(document, method, url, base_url=None, server_variables=None, document_url=None):
    if document_url is not None:
        document_url = validate_document_url(document_url)
    supplied = validate_server_variables(server_variables) if server_variables is not None else {}
    try:
        path = urlsplit(url).path or '/'
    except ValueError as error:
        raise ContractError('Invalid response URL') from error
    matches = []
    for template, verb, operation, path_item in operations(document):
        if verb != method.lower():
            continue
        # Presence, including an empty array, overrides the less-specific scope.
        overridden = 'servers' in operation or 'servers' in path_item
        servers = operation.get('servers', path_item.get('servers', document.get('servers', [])))
        if not isinstance(servers, list):
            raise ContractError('Invalid server collection')
        prefixes = set()
        for server in servers:
            try:
                prefixes.add(_server_prefix(server, supplied, document_url))
            except ContractError:
                if not supplied:
                    raise
                # A variable may belong to a different operation/server in this document.
                continue
        if not servers and not supplied:
            prefixes.add('')
        # The project base URL remains an alias only for operations without an override.
        if base_url and not overridden and not supplied and document_url is None:
            prefixes.add(_server_prefix({'url': base_url}))
        candidates = set()
        for prefix in prefixes:
            if not prefix:
                candidates.add(path)
            elif path == prefix or path.startswith(prefix + '/'):
                candidates.add(path[len(prefix):] or '/')
        pattern = '^' + re.sub(r'\\\{[^}]+\\\}', '[^/]+', re.escape(template)) + '$'
        if any(re.fullmatch(pattern, candidate) for candidate in candidates):
            matches.append((template.count('{'), template, operation))
    if not matches:
        raise ContractError('No matching OpenAPI operation')
    matches.sort(key=lambda item: item[0])
    if len(matches) > 1 and matches[0][0] == matches[1][0]:
        raise ContractError('Ambiguous OpenAPI operation')
    return matches[0][1:]


def _strict_json(value):
    def reject_constant(_):
        raise ValueError('Non-JSON number')

    def finite_float(text):
        number = float(text)
        if not math.isfinite(number):
            raise ValueError('Non-finite number')
        return number

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON member')
            result[key] = value
        return result

    return json.loads(value, parse_constant=reject_constant, parse_float=finite_float,
                      object_pairs_hook=unique_object)


def _header_type(schema):
    value = schema.get('type') if isinstance(schema, dict) else None
    if isinstance(value, list):
        non_null = [item for item in value if item != 'null']
        return non_null[0] if len(non_null) == 1 else None
    return value


def _header_primitive_type(document, schema):
    primitives = ('string', 'integer', 'number', 'boolean')
    direct = _header_type(schema)
    if direct in primitives:
        return direct
    active = set()
    remaining = 128

    def single_type(types):
        if types == {'integer', 'number'}:
            return 'integer'
        return next(iter(types)) if len(types) == 1 else None

    def collect(value, depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 32 or id(value) in active:
            raise ValueError('Header type traversal limit')
        if value is True:
            return set()
        if not isinstance(value, dict) or any(key in value for key in ('not', 'if')):
            raise ValueError('Ambiguous header type')
        active.add(id(value))
        types = set()
        try:
            if '$ref' in value:
                types.update(collect(pointer(document, value['$ref']), depth + 1))
            if 'type' in value:
                kind = _header_type(value)
                if kind not in primitives:
                    raise ValueError('Non-primitive header type')
                types.add(kind)
            for child in value.get('allOf', []):
                types.update(collect(child, depth + 1))
            for keyword in ('anyOf', 'oneOf'):
                if keyword in value:
                    branches = {single_type(collect(child, depth + 1)) for child in value[keyword]}
                    if len(branches) != 1 or None in branches:
                        raise ValueError('Ambiguous union header type')
                    types.update(branches)
            return types
        finally:
            active.remove(id(value))

    try:
        return single_type(collect(schema))
    except (ValueError, ContractError):
        return None


def _header_allof_array_items(document, schema):
    # This is a decoding view only; validate against the original schema below.
    if not isinstance(schema, dict) or 'allOf' not in schema:
        return None
    active, types, items = set(), set(), []
    remaining = 128

    def collect(value, depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 32 or id(value) in active:
            raise ValueError('Header array traversal limit')
        if value is True:
            return
        if not isinstance(value, dict) or any(key in value for key in ('anyOf', 'oneOf', 'not', 'if', 'prefixItems')):
            raise ValueError('Unsupported array composition')
        active.add(id(value))
        try:
            if '$ref' in value:
                collect(pointer(document, value['$ref']), depth + 1)
            if 'type' in value:
                types.add(_header_type(value))
            if 'items' in value:
                items.append(value['items'])
            for child in value.get('allOf', []):
                collect(child, depth + 1)
        finally:
            active.remove(id(value))

    try:
        collect(schema)
    except (ValueError, ContractError):
        return None
    if types != {'array'} or not items:
        return None
    return {'allOf': items}


def _header_allof_object_schema(document, schema):
    if not isinstance(schema, dict) or 'allOf' not in schema:
        return None
    active, types, nodes = set(), set(), []
    remaining = 128

    def collect(value, depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 32 or id(value) in active:
            raise ValueError('Header object traversal limit')
        if value is True:
            return
        if not isinstance(value, dict) or any(key in value for key in (
                'anyOf', 'oneOf', 'not', 'if', 'patternProperties', 'dependentSchemas', 'unevaluatedProperties')):
            raise ValueError('Unsupported object composition')
        active.add(id(value))
        try:
            if '$ref' in value:
                collect(pointer(document, value['$ref']), depth + 1)
            if 'type' in value:
                types.add(_header_type(value))
            nodes.append(value)
            for child in value.get('allOf', []):
                collect(child, depth + 1)
        finally:
            active.remove(id(value))

    try:
        collect(schema)
    except (ValueError, ContractError):
        return None
    if types != {'object'}:
        return None
    properties = {}
    names = {name for node in nodes for name in node.get('properties', {})}
    for name in names:
        # additionalProperties applies within each subschema, not globally.
        constraints = [node.get('properties', {}).get(name, node.get('additionalProperties', True)) for node in nodes]
        properties[name] = {'allOf': [value for value in constraints if isinstance(value, dict)]}
    additional = [node['additionalProperties'] for node in nodes if isinstance(node.get('additionalProperties'), dict)]
    # false/required/size constraints stay in the original validation schema.
    return {'type': 'object', 'properties': properties,
            'additionalProperties': {'allOf': additional} if additional else True}


def _header_scalar(schema, value, document):
    schema_type = _header_primitive_type(document, schema)
    try:
        if schema_type == 'integer':
            return int(value)
        if schema_type == 'number':
            number = float(value)
            return number if math.isfinite(number) else value
        if schema_type == 'boolean' and value in ('true', 'false'):
            return value == 'true'
    except ValueError:
        pass
    return value


def _header_object(document, header, schema, raw):
    if header.get('style', 'simple') != 'simple' or any(
            key in schema for key in ('allOf', 'anyOf', 'oneOf', 'patternProperties', 'dependentSchemas')):
        return None, 'unsupported_header_serialization'
    properties = {key: resolve(document, value) for key, value in schema.get('properties', {}).items()}
    additional = schema.get('additionalProperties', True)
    if isinstance(additional, dict):
        additional = resolve(document, additional)
    decoders = list(properties.values()) + ([additional] if isinstance(additional, dict) else [])
    if any(not isinstance(value, dict) or _header_primitive_type(document, value) not in
           ('string', 'integer', 'number', 'boolean') for value in decoders):
        return None, 'unsupported_header_serialization'
    parts = raw.split(',') if raw else []
    if header.get('explode', False):
        if any('=' not in part for part in parts):
            return None, 'invalid_header_serialization'
        pairs = [part.split('=', 1) for part in parts]
    else:
        if len(parts) % 2:
            return None, 'invalid_header_serialization'
        pairs = zip(parts[::2], parts[1::2])
    result = {}
    for key, value in pairs:
        key, value = key.strip(' \t'), value.strip(' \t')
        if not key or key in result:
            return None, 'invalid_header_serialization'
        decoder = properties.get(key, additional)
        result[key] = _header_scalar(decoder, value, document)
    return result, None


def validate_response(document, method, url, status, headers, body, *, raw_body=None, base_url=None, server_variables=None, document_url=None):
    errors = [item for item in lint(document) if item['severity'] == 'error']
    if errors:
        return {'valid': False, 'issues': errors}
    try:
        path, operation = match_operation(document, method, url, base_url, server_variables, document_url)
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
                content = header.get('content', {})
                if len(content) != 1:
                    errors.append(issue('unsupported_header_content', location))
                    continue
                media, definition = next(iter(content.items()))
                media = media.split(';', 1)[0].strip().lower()
                if media == 'text/plain':
                    value = normalized[name.lower()]
                elif re.fullmatch(r'application/(?:json|[^\s/*;]+\+json)', media):
                    try:
                        value = _strict_json(normalized[name.lower()])
                    except (ValueError, TypeError, RecursionError):
                        errors.append(issue('invalid_header_json', location))
                        continue
                else:
                    errors.append(issue('unsupported_header_content', location))
                    continue
                if 'schema' in definition:
                    errors.extend(schema_errors(document, definition['schema'], value, location))
                continue
            schema = resolve(document, header['schema'])
            value = normalized[name.lower()]
            composed_items = _header_allof_array_items(document, schema)
            composed_object = _header_allof_object_schema(document, schema)
            if isinstance(schema, dict) and (_header_type(schema) == 'array' or composed_items is not None):
                items = composed_items if composed_items is not None else resolve(document, schema.get('items', {}))
                # Only homogeneous primitive arrays have an unambiguous decoder here.
                if (header.get('style', 'simple') != 'simple' or 'prefixItems' in schema or
                        not isinstance(items, dict) or
                        _header_primitive_type(document, items) not in ('string', 'integer', 'number', 'boolean')):
                    errors.append(issue('unsupported_header_serialization', location))
                    continue
                value = [_header_scalar(items, part.strip(' \t'), document) for part in value.split(',')]
            elif isinstance(schema, dict) and (_header_type(schema) == 'object' or composed_object is not None):
                value, code = _header_object(document, header, composed_object if composed_object is not None else schema, value)
                if code:
                    errors.append(issue(code, location))
                    continue
            else:
                value = _header_scalar(schema, value, document)
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
            else:
                if raw_body is not None and (media == 'application/json' or media.endswith('+json')):
                    try:
                        body = _strict_json(raw_body)
                    except (ValueError, TypeError, RecursionError):
                        errors.append(issue('invalid_json', '#/response/body'))
                        return {'valid': False, 'issues': errors}
                if 'schema' in media_schema:
                    errors.extend(schema_errors(document, media_schema['schema'], body, '#/response/body'))
        return {'valid': not errors, 'operation': method.upper() + ' ' + path, 'issues': errors[:100]}
    except ContractError:
        return {'valid': False, 'issues': [issue('operation_or_reference_error', '#/response')]}
