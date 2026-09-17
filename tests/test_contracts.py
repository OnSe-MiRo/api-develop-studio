from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from api_test.contracts import compare, lint, validate_response, ContractError, load_file
from api_test.contracts.documents import bundle_document


def document(version='3.0.3'):
    return {'openapi': version, 'info': {'title': 'Fixture', 'version': '1'}, 'paths': {
        '/items/{id}': {'get': {'operationId': 'getItem', 'summary': 'Get item',
            'parameters': [{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}],
            'responses': {'200': {'description': 'OK', 'headers': {'X-Count': {'required': True, 'schema': {'type': 'integer'}}},
                'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Item'}}}}}}}},
        'components': {'schemas': {'Item': {'type': 'object', 'required': ['id'], 'properties': {'id': {'type': 'integer'}}}}}}


class ContractTests(unittest.TestCase):
    def test_lint_versions_and_safe_reference_errors(self):
        for version in ['3.0.3', '3.1.0']:
            self.assertEqual(lint(document(version)), [])
        bad = document()
        bad['paths']['/items/{id}']['get']['operationId'] = ''
        self.assertTrue(any(issue['severity'] == 'warning' for issue in lint(bad)))
        bad['components']['schemas']['Item'] = {'$ref': 'http://169.254.169.254/private-secret'}
        issues = lint(bad)
        self.assertEqual(issues[0]['code'], 'unresolved_or_external_ref')
        self.assertNotIn('private-secret', json.dumps(issues))
        bad['components']['schemas']['Item'] = {'$ref': '#/missing'}
        self.assertFalse(compare(document(), bad)['compatible'])

    def test_valid_response_media_headers_format_and_no_value_leak(self):
        doc = document()
        result = validate_response(doc, 'GET', 'https://example.test/api/items/1', 200,
                                   {'Content-Type': 'application/json; charset=utf-8', 'x-count': '2'}, {'id': 1}, base_url='https://example.test/api')
        self.assertTrue(result['valid'], result)
        for status, headers, body, expected in [
            (404, {}, {}, 'undocumented_status'),
            (200, {'Content-Type': 'text/html', 'X-Count': '1'}, 'secret-value', 'undocumented_content_type'),
            (200, {'Content-Type': 'application/json'}, {'id': 1}, 'missing_header'),
            (200, {'Content-Type': 'application/json', 'X-Count': 'bad-secret'}, {'id': 'secret-value'}, 'schema_type'),
        ]:
            result = validate_response(doc, 'GET', '/items/1', status, headers, body)
            self.assertFalse(result['valid'])
            self.assertIn(expected, [item['code'] for item in result['issues']])
            self.assertNotIn('secret', json.dumps(result))
        result = validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'X-Count': '1'}, 'bad', raw_body='bad')
        self.assertIn('invalid_json', [item['code'] for item in result['issues']])

    def test_recursive_schema_and_nullable_30(self):
        doc = document()
        doc['components']['schemas']['Item']['properties']['next'] = {'$ref': '#/components/schemas/Item'}
        doc['components']['schemas']['Item']['properties']['name'] = {'type': 'string', 'nullable': True}
        self.assertEqual(lint(doc), [])
        self.assertTrue(validate_response(doc, 'get', '/items/1', 200, {'content-type': 'application/json', 'x-count': '1'}, {'id': 1, 'next': {'id': 2}, 'name': None})['valid'])
        changed = deepcopy(doc)
        changed['components']['schemas']['Item']['properties']['id']['type'] = 'string'
        self.assertIn('type_changed', [item['code'] for item in compare(doc, changed)['changes']])

    def test_compatible_and_breaking_changes(self):
        old = document()
        changed = deepcopy(old)
        changed['paths']['/items/{id}']['get']['summary'] = 'Description only'
        changed['components']['schemas']['Item']['properties']['optional'] = {'type': 'string'}
        self.assertTrue(compare(old, changed)['compatible'])
        for mutate, code in [
            (lambda doc: doc['paths'].clear(), 'operation_removed'),
            (lambda doc: doc['components']['schemas']['Item']['properties']['id'].update(type='string'), 'type_changed'),
            (lambda doc: doc['components']['schemas']['Item'].pop('required'), 'required_removed'),
            (lambda doc: doc['paths']['/items/{id}']['get']['responses'].update({'201': doc['paths']['/items/{id}']['get']['responses'].pop('200')}), 'response_removed'),
            (lambda doc: doc['paths']['/items/{id}']['get']['parameters'].append({'name': 'token', 'in': 'query', 'required': True, 'schema': {'type': 'string'}}), 'required_parameter_added'),
        ]:
            new = deepcopy(old); mutate(new)
            result = compare(old, new)
            self.assertFalse(result['compatible'], result)
            self.assertIn(code, [item['code'] for item in result['changes']], result)

    def test_request_required_and_enum_direction(self):
        old = document()
        old['paths']['/items/{id}']['get']['requestBody'] = {'content': {'application/json': {'schema': {'type': 'object', 'properties': {'name': {'type': 'string', 'enum': ['a', 'b']}}}}}}
        new = deepcopy(old)
        schema = new['paths']['/items/{id}']['get']['requestBody']['content']['application/json']['schema']
        schema['required'] = ['name']
        schema['properties']['name']['enum'] = ['a']
        codes = [item['code'] for item in compare(old, new)['changes']]
        self.assertIn('required_added', codes)
        self.assertIn('enum_contract_changed', codes)

    def test_hash_bound_approval_and_stale_rejection(self):
        old = document(); new = deepcopy(old); new['paths'].clear()
        result = compare(old, new)
        approvals = {key: result[key] for key in ('baselineHash', 'currentHash')}
        approvals['approvals'] = [{'id': item['id'], 'reason': 'Scheduled retirement', 'approvedBy': 'reviewer'} for item in result['changes']]
        self.assertTrue(compare(old, new, approvals)['compatible'])
        new['info']['version'] = '2'
        with self.assertRaises(ContractError): compare(old, new, approvals)
        with self.assertRaises(ContractError): compare(old, document(), {})

    def test_bundle_refs_remain_recursive_and_cli_blocks(self):
        doc = document()
        doc['components']['schemas']['Item']['properties']['next'] = {'$ref': '#/components/schemas/Item'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'old.json').write_text(json.dumps(doc))
            new = deepcopy(doc); new['paths'].clear()
            (root / 'new.json').write_text(json.dumps(new))
            loaded = load_file(root / 'old.json')
            self.assertEqual(lint(loaded), [])
            result = subprocess.run([sys.executable, '-m', 'api_test.contracts', str(root / 'new.json'), '--baseline', str(root / 'old.json')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse(json.loads(result.stdout)['compatible'])
            report = json.loads(result.stdout)
            approvals = {key: report[key] for key in ('baselineHash', 'currentHash')}
            approvals['approvals'] = [{'id': item['id'], 'reason': 'Fixture retirement', 'approvedBy': 'test-reviewer'} for item in report['changes']]
            (root / 'approvals.json').write_text(json.dumps(approvals))
            command = [sys.executable, '-m', 'api_test.contracts', str(root / 'new.json'), '--baseline', str(root / 'old.json'), '--approvals', str(root / 'approvals.json')]
            approved = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(approved.returncode, 0, approved.stderr)
            self.assertTrue(json.loads(approved.stdout)['changes'][0]['approved'])
            new['info']['version'] = 'changed-again'
            (root / 'new.json').write_text(json.dumps(new))
            stale = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(stale.returncode, 2, stale.stderr)

            (root / 'bad.yaml').write_text('openapi: 3.0.3\npaths: {$ref: ../escape.yaml}')
            with self.assertRaises(ContractError): load_file(root / 'bad.yaml')

    def test_bundled_header_and_security_component_changes(self):
        old = document()
        old['components']['headers'] = {'Count': {'schema': {'type': 'integer'}}}
        old['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Count'] = {'$ref': '#/components/headers/Count'}
        new = deepcopy(old); new['components']['headers']['Count']['schema']['type'] = 'string'
        self.assertIn('response_headers_changed', [item['code'] for item in compare(old, new)['changes']])

    def test_nested_component_changes_cannot_hide_behind_unchanged_refs(self):
        old = document()
        old['components']['schemas']['Item']['properties']['child'] = {'$ref': '#/components/schemas/Child'}
        old['components']['schemas']['Child'] = {'type': 'string'}
        new = deepcopy(old)
        new['components']['schemas']['Child']['type'] = 'integer'
        self.assertIn('type_changed', [item['code'] for item in compare(old, new)['changes']])
        old['components']['schemas']['Item']['properties']['child'] = {'allOf': [{'$ref': '#/components/schemas/Child'}]}
        new = deepcopy(old)
        new['components']['schemas']['Child']['type'] = 'integer'
        self.assertFalse(compare(old, new)['compatible'])

    def test_default_range_status_json31_and_unsupported_scope(self):
        doc = document('3.1.0')
        op = doc['paths']['/items/{id}']['get']
        op['responses']['2XX'] = op['responses'].pop('200')
        schema = doc['components']['schemas']['Item']
        schema['properties']['date'] = {'type': ['string', 'null'], 'format': 'date'}
        headers = {'content-type': 'application/json', 'X-Count': '1'}
        self.assertTrue(validate_response(doc, 'GET', '/items/1', 201, headers, {'id': 1, 'date': None})['valid'])
        self.assertFalse(validate_response(doc, 'GET', '/items/1', 201, headers, {'id': 1, 'date': 'wrong'})['valid'])
        schema['$id'] = 'https://example.test/remote'
        self.assertIn('unsupported_reference_scope', [item['code'] for item in lint(doc)])

    def test_read_only_response_and_write_only_required(self):
        doc = document()
        schema = doc['components']['schemas']['Item']
        schema['required'].append('password')
        schema['properties']['password'] = {'type': 'string', 'writeOnly': True}
        self.assertTrue(validate_response(doc, 'GET', '/items/1', 200, {'content-type': 'application/json', 'X-Count': '1'}, {'id': 1})['valid'])

    def test_read_context_31_and_composition_field_names(self):
        doc = document('3.1.0')
        schema = doc['components']['schemas']['Item']
        schema['required'].append('password')
        schema['properties']['password'] = {'type': 'string', 'writeOnly': True}
        self.assertTrue(validate_response(doc, 'GET', '/items/1', 200, {'content-type': 'application/json', 'X-Count': '1'}, {'id': 1})['valid'])
        old = document()
        old['components']['schemas']['Item']['allOf'] = [{'properties': {'description': {'type': 'string'}}}]
        new = deepcopy(old)
        new['components']['schemas']['Item']['allOf'][0]['properties']['description']['type'] = 'integer'
        self.assertFalse(compare(old, new)['compatible'])

    def test_malformed_dialect_and_boolean_header_schema_fail_safely(self):
        doc = document('3.1.0')
        doc['jsonSchemaDialect'] = []
        self.assertEqual(lint(doc)[0]['code'], 'unsupported_schema_dialect')
        del doc['jsonSchemaDialect']
        doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Count']['schema'] = True
        self.assertTrue(validate_response(doc, 'GET', '/items/1', 200, {'content-type': 'application/json', 'X-Count': 'anything'}, {'id': 1})['valid'])
