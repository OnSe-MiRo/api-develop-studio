import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
from test_contracts import document


class NullableHeaderTests(unittest.TestCase):
    def spec(self, schema, version='3.1.0'):
        doc = document(version)
        doc['components']['schemas']['Header'] = schema
        doc['paths']['/items/{id}']['get']['responses']['200']['headers'] = {
            'X-Value': {'required': True, 'schema': {'$ref': '#/components/schemas/Header'}}}
        return doc

    def check(self, doc, raw):
        return validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'x-value': raw}, {'id': 1})

    def test_scalar_types_orders_singletons_and_30_compatibility(self):
        for kind, raw in [('integer', '2'), ('number', '1.5'), ('boolean', 'true'), ('string', 'text')]:
            for types in [[kind, 'null'], ['null', kind], [kind]]:
                with self.subTest(types=types):
                    self.assertTrue(self.check(self.spec({'type': types}), raw)['valid'])
            self.assertTrue(self.check(self.spec({'type': kind, 'nullable': True}, '3.0.3'), raw)['valid'])
        self.assertFalse(self.check(self.spec({'type': ['integer', 'null']}, '3.0.3'), '2')['valid'])

    def test_array_object_and_map_nullable_types_with_refs(self):
        doc = self.spec({'type': ['array', 'null'], 'items': {'$ref': '#/components/schemas/HeaderItem'}, 'minItems': 2})
        doc['components']['schemas']['HeaderItem'] = {'type': ['integer', 'null'], 'minimum': 1}
        self.assertTrue(self.check(doc, '1,2')['valid'])
        self.assertFalse(self.check(doc, '1,0')['valid'])
        self.assertFalse(self.check(doc, '1,null')['valid'])
        schema = {'type': ['object', 'null'], 'required': ['id'], 'properties': {'id': {'type': ['integer', 'null']}}, 'additionalProperties': {'type': ['boolean', 'null']}}
        doc = self.spec(schema)
        self.assertTrue(self.check(doc, 'id,2,enabled,true')['valid'])
        doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Value']['explode'] = True
        self.assertTrue(self.check(doc, 'id=2,enabled=false')['valid'])
        self.assertFalse(self.check(doc, 'id=null,enabled=true')['valid'])

    def test_null_is_not_inferred_and_required_is_independent(self):
        doc = self.spec({'type': ['integer', 'null']})
        for raw in ['', 'null', 'PRIVATE']:
            result = self.check(doc, raw)
            self.assertIn('schema_type', [i['code'] for i in result['issues']])
            self.assertNotIn('PRIVATE', json.dumps(result))
        missing = validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json'}, {'id': 1})
        self.assertIn('missing_header', [i['code'] for i in missing['issues']])
        self.assertTrue(self.check(self.spec({'type': ['string', 'null'], 'enum': ['null']}), 'null')['valid'])
        header = doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Value']
        schema = header.pop('schema'); header['content'] = {'application/json': {'schema': schema}}
        self.assertTrue(self.check(doc, 'null')['valid'])
        header['content'] = {'text/plain': {'schema': schema}}
        self.assertFalse(self.check(doc, 'null')['valid'])

    def test_ambiguous_union_is_not_coerced(self):
        doc = self.spec({'type': ['integer', 'boolean', 'null']})
        self.assertFalse(self.check(doc, '1')['valid'])
        for schema in [
            {'type': 'array', 'items': {'type': ['integer', 'string', 'null']}},
            {'type': 'object', 'properties': {'id': {'type': ['integer', 'string', 'null']}}},
        ]:
            result = self.check(self.spec(schema), 'id,1')
            self.assertIn('unsupported_header_serialization', [i['code'] for i in result['issues']])
        result = self.check(self.spec({'type': ['integer', 'null'], 'enum': [3, None]}), '2')
        self.assertIn('schema_enum', [i['code'] for i in result['issues']])

    def test_real_http_nullable_array_runner(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                body = b'{"id":1}'
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('X-Value', '1,2' if self.path.endswith('/1') else '1,null')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 2); self.addCleanup(server.shutdown)
        doc = self.spec({'type': ['array', 'null'], 'items': {'type': ['integer', 'null']}})
        for suffix, expected in [('1', 'passed'), ('2', 'failed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
            result = ApiTestRunner().run_case('nullable-header', case, contract_document=doc)
            self.assertEqual(result.status, expected)
            self.assertEqual(result.contract['valid'], expected == 'passed')
