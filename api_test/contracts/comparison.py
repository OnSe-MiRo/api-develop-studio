"""Conservative directional compatibility checks; uncertain changes require review."""
import hashlib
from .documents import ContractError, digest, escape, resolve
from .validation import lint, operations

ANNOTATIONS = {'title', 'description', 'example', 'examples', 'externalDocs', 'deprecated'}


def semantic(document, value, seen=None):
    seen = set() if seen is None else seen
    value = resolve(document, value)
    if isinstance(value, (dict, list)):
        if id(value) in seen:
            return '<recursive>'
        seen = seen | {id(value)}
    if isinstance(value, dict):
        return {key: semantic(document, item, seen) for key, item in value.items()}
    if isinstance(value, list):
        return [semantic(document, item, seen) for item in value]
    return value


def compare(baseline, current, approvals=None):
    old_hash, new_hash = digest(baseline), digest(current)
    issues = [{**item, 'source': source} for source, doc in [('baseline', baseline), ('current', current)] for item in lint(doc)]
    changes = []
    def add(code, path, severity='breaking'):
        identifier = hashlib.sha256((old_hash + new_hash + code + path).encode()).hexdigest()[:24]
        if not any(item['id'] == identifier for item in changes):
            changes.append({'id': identifier, 'code': code, 'path': path, 'severity': severity, 'approved': False})
    def schema(old, new, path, direction, seen=None):
        old, new = resolve(baseline, old), resolve(current, new)
        seen = set() if seen is None else seen
        pair = (id(old), id(new), direction)
        if pair in seen:
            return
        seen = seen | {pair}
        if not isinstance(old, dict) or not isinstance(new, dict):
            if old != new:
                add('schema_changed', path, 'review')
            return
        handled = {'properties', 'required', 'items', 'type', 'enum', 'nullable', '$ref'} | ANNOTATIONS
        if old.get('type') != new.get('type') or old.get('nullable', False) != new.get('nullable', False):
            add('type_changed', path)
        if old.get('enum') != new.get('enum'):
            a, b = old.get('enum'), new.get('enum')
            narrowed = b is not None and (a is None or any(value not in b for value in a))
            widened = a is not None and (b is None or any(value not in a for value in b))
            if (narrowed if direction == 'request' else widened):
                add('enum_contract_changed', path)
        a, b = set(old.get('required', [])), set(new.get('required', []))
        for name in sorted(b - a if direction == 'request' else a - b):
            add('required_added' if direction == 'request' else 'required_removed', path + '/required/' + escape(name))
        old_props, new_props = old.get('properties', {}), new.get('properties', {})
        for name, value in old_props.items():
            location = path + '/properties/' + escape(name)
            if name not in new_props:
                add('property_removed', location)
            else:
                schema(value, new_props[name], location, direction, seen)
        if direction == 'response' and old.get('additionalProperties') is False:
            for name in new_props.keys() - old_props.keys():
                add('response_property_added_to_closed_schema', path + '/properties/' + escape(name), 'review')
        if 'items' in old or 'items' in new:
            schema(old.get('items', {}), new.get('items', {}), path + '/items', direction, seen)
        for key in old.keys() | new.keys():
            if key not in handled and semantic(baseline, old.get(key)) != semantic(current, new.get(key)):
                add('schema_constraint_changed', path + '/' + escape(key), 'review')
    def media(old, new, path, direction):
        for name, value in old.items():
            location = path + '/' + escape(name)
            if name not in new:
                add('media_type_removed', location)
            else:
                schema(value.get('schema', {}), new[name].get('schema', {}), location + '/schema', direction)
                if semantic(baseline, value.get('encoding')) != semantic(current, new[name].get('encoding')):
                    add('media_encoding_changed', location + '/encoding', 'review')
        if direction == 'response':
            for name in new.keys() - old.keys():
                add('response_media_added', path + '/' + escape(name), 'review')
    def parameters(doc, operation, item):
        result = {}
        for raw in [*item.get('parameters', []), *operation.get('parameters', [])]:
            value = resolve(doc, raw)
            result[(value['in'], value['name'])] = value
        return result
    if not any(item['severity'] == 'error' for item in issues):
        try:
            old_ops = {(path, method): (op, item) for path, method, op, item in operations(baseline)}
            new_ops = {(path, method): (op, item) for path, method, op, item in operations(current)}
            if baseline.get('openapi') != current.get('openapi'):
                add('openapi_version_changed', '#/openapi', 'review')
            if baseline.get('servers') != current.get('servers'):
                add('servers_changed', '#/servers', 'review')
            if semantic(baseline, baseline.get('components', {}).get('securitySchemes')) != semantic(current, current.get('components', {}).get('securitySchemes')):
                add('security_schemes_changed', '#/components/securitySchemes', 'review')
            for key, (old, old_item) in old_ops.items():
                path, method = key
                location = '#/paths/' + escape(path) + '/' + method
                if key not in new_ops:
                    add('operation_removed', location)
                    continue
                new, new_item = new_ops[key]
                for field in ('security', 'servers'):
                    a = old.get(field, old_item.get(field, baseline.get(field)))
                    b = new.get(field, new_item.get(field, current.get(field)))
                    if a != b:
                        add(field + '_changed', location + '/' + field, 'review')
                if old.get('operationId') != new.get('operationId'):
                    add('operation_id_changed', location + '/operationId', 'review')
                a, b = parameters(baseline, old, old_item), parameters(current, new, new_item)
                for param, value in a.items():
                    target = location + '/parameters/' + escape(':'.join(param))
                    if param not in b:
                        add('parameter_removed', target)
                    else:
                        if not value.get('required') and b[param].get('required'):
                            add('required_added', target)
                        schema(value.get('schema', {}), b[param].get('schema', {}), target + '/schema', 'request')
                        for field in ('content', 'style', 'explode', 'allowEmptyValue', 'allowReserved'):
                            if value.get(field) != b[param].get(field):
                                add('parameter_encoding_changed', target + '/' + field, 'review')
                for param in b.keys() - a.keys():
                    if b[param].get('required'):
                        add('required_parameter_added', location + '/parameters/' + escape(':'.join(param)))
                old_body, new_body = resolve(baseline, old.get('requestBody', {})), resolve(current, new.get('requestBody', {}))
                if new_body.get('required') and not old_body.get('required'):
                    add('required_request_body_added', location + '/requestBody')
                media(old_body.get('content', {}), new_body.get('content', {}), location + '/requestBody/content', 'request')
                for status, raw in old['responses'].items():
                    target = location + '/responses/' + escape(status)
                    if status not in new['responses']:
                        add('response_removed', target)
                        continue
                    a_response, b_response = resolve(baseline, raw), resolve(current, new['responses'][status])
                    media(a_response.get('content', {}), b_response.get('content', {}), target + '/content', 'response')
                    if semantic(baseline, a_response.get('headers')) != semantic(current, b_response.get('headers')):
                        add('response_headers_changed', target + '/headers', 'review')
                    if semantic(baseline, a_response.get('links')) != semantic(current, b_response.get('links')):
                        add('response_links_changed', target + '/links', 'review')
                for status in new['responses'].keys() - old['responses'].keys():
                    if 'default' not in old['responses'] and status[0] + 'XX' not in old['responses']:
                        add('response_status_added', location + '/responses/' + escape(status), 'review')
                if semantic(baseline, old.get('callbacks')) != semantic(current, new.get('callbacks')):
                    add('callbacks_changed', location + '/callbacks', 'review')
            if semantic(baseline, baseline.get('webhooks')) != semantic(current, current.get('webhooks')):
                add('webhooks_changed', '#/webhooks', 'review')
        except (ContractError, ValueError, TypeError, KeyError, RecursionError):
            issues.append({'code': 'comparison_incomplete', 'severity': 'error', 'path': '#', 'message': '호환성 분석을 완료할 수 없습니다.'})
    if approvals is not None:
        if not isinstance(approvals, dict) or approvals.get('baselineHash') != old_hash or approvals.get('currentHash') != new_hash or not isinstance(approvals.get('approvals'), list):
            raise ContractError('Approval record must match both contract hashes')
        indexed = {item['id']: item for item in changes}
        for approval in approvals['approvals']:
            if not isinstance(approval, dict) or approval.get('id') not in indexed or not all(isinstance(approval.get(field), str) and approval[field].strip() for field in ('reason', 'approvedBy')):
                raise ContractError('Approval requires a known change ID, reason and approvedBy')
            indexed[approval['id']].update(approved=True, approval={'reason': approval['reason'], 'approvedBy': approval['approvedBy']})
    return {'baselineHash': old_hash, 'currentHash': new_hash, 'issues': issues, 'changes': changes,
            'compatible': not any(item['severity'] == 'error' for item in issues) and not any(not item['approved'] for item in changes)}
