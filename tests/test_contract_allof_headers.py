import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
from test_contracts import document


class AllOfHeaderTests(unittest.TestCase):
    def spec(self, schema, version='3.0.3'):
        doc = document(version)
        doc['components']['schemas']['HeaderBase'] = {'type': 'integer', 'minimum': 1}
        doc['paths']['/items/{id}']['get']['responses']['200']['headers'] = {'X-Value': {'required': True, 'schema': schema}}
        return doc

    def check(self, doc, value):
        return validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'X-Value': value}, {'id': 1})

    def test_infers_primitives_and_preserves_all_constraints(self):
        for version in ['3.0.3', '3.1.0']:
            for kind, raw in [('integer', '2'), ('number', '1.5'), ('boolean', 'true'), ('string', 'text')]:
                schema = {'allOf': [{'type': kind}, {}]}
                self.assertTrue(self.check(self.spec(schema, version), raw)['valid'])
            schema = {'allOf': [{'$ref': '#/components/schemas/HeaderBase'}, {'allOf': [{'maximum': 3}, {'enum': [2, 3]}]}]}
            doc = self.spec(schema, version)
            self.assertTrue(self.check(doc, '2')['valid'])
            for raw, code in [('0', 'schema_minimum'), ('4', 'schema_maximum'), ('1', 'schema_enum'), ('PRIVATE', 'schema_type')]:
                result = self.check(doc, raw)
                self.assertIn(code, [i['code'] for i in result['issues']])
                self.assertNotIn('PRIVATE', json.dumps(result))

    def test_array_items_object_fields_and_maps(self):
        item = {'allOf': [{'$ref': '#/components/schemas/HeaderBase'}, {'maximum': 3}]}
        for version in ['3.0.3', '3.1.0']:
            for schema, good, bad in [
                ({'type': 'array', 'items': item}, '1,2', '1,4'),
                ({'type': 'object', 'properties': {'id': item}, 'required': ['id']}, 'id,2', 'id,4'),
                ({'type': 'object', 'additionalProperties': item}, 'a,1,b,2', 'a,4'),
            ]:
                self.assertTrue(self.check(self.spec(schema, version), good)['valid'])
                self.assertFalse(self.check(self.spec(schema, version), bad)['valid'])

    def test_numeric_intersection_nullable_and_direct_type_compatibility(self):
        schema = {'allOf': [{'type': 'number'}, {'type': 'integer'}]}
        self.assertTrue(self.check(self.spec(schema), '2')['valid'])
        self.assertFalse(self.check(self.spec(schema), '1.5')['valid'])
        schema = {'allOf': [{'type': ['integer', 'null']}, {'minimum': 1}]}
        self.assertTrue(self.check(self.spec(schema, '3.1.0'), '2')['valid'])
        self.assertFalse(self.check(self.spec(schema, '3.1.0'), 'null')['valid'])
        schema = {'type': 'integer', 'anyOf': [{'enum': [1]}, {'enum': [2]}]}
        self.assertTrue(self.check(self.spec(schema), '2')['valid'])

    def test_ambiguous_container_and_cycle_fail_safely(self):
        for item in [
            {'allOf': [{'type': 'integer'}, {'type': 'string'}]},
            {'allOf': [{'anyOf': [{'type': 'integer'}, {'type': 'string'}]}]},
            {'allOf': [{'type': 'object'}]},
        ]:
            result = self.check(self.spec({'type': 'array', 'items': item}), 'PRIVATE')
            self.assertIn('unsupported_header_serialization', [i['code'] for i in result['issues']])
            self.assertNotIn('PRIVATE', json.dumps(result))
        doc = self.spec({'type': 'array', 'items': {'$ref': '#/components/schemas/HeaderBase'}})
        doc['components']['schemas']['HeaderBase'] = {'allOf': [{'$ref': '#/components/schemas/HeaderBase'}]}
        self.assertFalse(self.check(doc, '1')['valid'])
        doc = self.spec({'type': 'array', 'items': {'allOf': [{'type': 'integer'}] * 130}})
        self.assertIn('unsupported_header_serialization', [i['code'] for i in self.check(doc, '1')['issues']])

    def test_real_http_runner_resolves_allof(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                body = b'{"id":1}'
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('X-Value', '2' if self.path.endswith('/1') else '0')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 2); self.addCleanup(server.shutdown)
        doc = self.spec({'allOf': [{'$ref': '#/components/schemas/HeaderBase'}, {'maximum': 3}]})
        for suffix, expected in [('1', 'passed'), ('2', 'failed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
            result = ApiTestRunner().run_case('allof-header', case, contract_document=doc)
            self.assertEqual(result.status, expected)
            self.assertEqual(result.contract['valid'], expected == 'passed')
