import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
from test_contracts import document


class LiteralHeaderTests(unittest.TestCase):
    def spec(self, schema, version='3.1.0'):
        doc = document(version)
        doc['paths']['/items/{id}']['get']['responses']['200']['headers'] = {'X-Value': {'schema': schema, 'required': True}}
        return doc

    def check(self, schema, raw, version='3.1.0'):
        return validate_response(self.spec(schema, version), 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'X-Value': raw}, {'id': 1})

    def test_enum_without_type_versions_and_primitive_values(self):
        for version in ['3.0.3', '3.1.0']:
            for values, good, bad in [([1, 2], '2', '3'), ([1, 2.5], '2.5', '3'), ([True, False], 'true', '1'), (['ready'], 'ready', 'PRIVATE')]:
                self.assertTrue(self.check({'enum': values}, good, version)['valid'])
                result = self.check({'enum': values}, bad, version)
                self.assertIn('schema_enum', [i['code'] for i in result['issues']])
                self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertTrue(self.check({'enum': [9007199254740993]}, '9007199254740993')['valid'])
        self.assertFalse(self.check({'enum': [9007199254740993]}, '9007199254740992')['valid'])
        self.assertTrue(self.check({'allOf': [{'type': 'number'}, {'enum': [2]}]}, '2.0')['valid'])

    def test_const_null_and_explicit_type_precedence(self):
        for value, raw in [(2, '2'), (2.5, '2.5'), (True, 'true'), ('ready', 'ready')]:
            self.assertTrue(self.check({'const': value}, raw)['valid'])
            self.assertFalse(self.check({'const': value}, 'PRIVATE')['valid'])
        self.assertTrue(self.check({'enum': [None, 2]}, '2')['valid'])
        self.assertFalse(self.check({'enum': [None, 2]}, 'null')['valid'])
        self.assertFalse(self.check({'type': 'string', 'enum': [2]}, '2')['valid'])
        self.assertFalse(self.check({'const': 2}, '2', '3.0.3')['valid'])

    def test_array_object_prefix_and_composition(self):
        for schema, good, bad in [
            ({'type': 'array', 'items': {'enum': [1, 2]}}, '1,2', '1,3'),
            ({'type': 'object', 'properties': {'id': {'const': 2}}}, 'id,2', 'id,3'),
            ({'type': 'array', 'prefixItems': [{'enum': ['ready']}, {'const': 2}], 'items': False}, 'ready,2', 'ready,3'),
            ({'oneOf': [{'const': 1}, {'const': 2}]}, '2', '3'),
        ]:
            self.assertTrue(self.check(schema, good)['valid'])
            self.assertFalse(self.check(schema, bad)['valid'])
        doc = self.spec({'$ref': '#/components/schemas/Header'})
        doc['components']['schemas']['Header'] = {'enum': [2]}
        self.assertTrue(validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'X-Value': '2'}, {'id': 1})['valid'])

    def test_ambiguous_structured_and_null_only_items_fail_closed(self):
        for values in [[1, '1'], [True, 1], [None], [{'id': 1}], [[1, 2]]]:
            result = self.check({'type': 'array', 'items': {'enum': values}}, 'PRIVATE')
            self.assertIn('unsupported_header_serialization', [i['code'] for i in result['issues']])
            self.assertNotIn('PRIVATE', json.dumps(result))

    def test_real_http_enum_only_header_runner(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                body = b'{"id":1}'
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('X-Value', '2' if self.path.endswith('/1') else '3')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 2); self.addCleanup(server.shutdown)
        for suffix, expected in [('1', 'passed'), ('2', 'failed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
            result = ApiTestRunner().run_case('literal-header', case, contract_document=self.spec({'enum': [1, 2]}))
            self.assertEqual(result.status, expected)
            self.assertEqual(result.contract['valid'], expected == 'passed')
