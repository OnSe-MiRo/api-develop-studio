import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
from test_contracts import document


class PrefixHeaderTests(unittest.TestCase):
    def spec(self, **changes):
        doc = document('3.1.0')
        doc['components']['schemas']['Count'] = {'type': ['integer', 'null'], 'minimum': 1}
        schema = {'type': 'array', 'prefixItems': [{'type': 'string', 'enum': ['ready']}, {'$ref': '#/components/schemas/Count'}, {'type': 'boolean'}], 'items': False}
        schema.update(changes)
        doc['paths']['/items/{id}']['get']['responses']['200']['headers'] = {'X-Tuple': {'required': True, 'schema': schema}}
        return doc

    def header(self, doc):
        return doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Tuple']

    def check(self, doc, value):
        return validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'x-tuple': value}, {'id': 1})

    def test_positions_refs_and_explode(self):
        doc = self.spec(minItems=3, type=['array', 'null'])
        for explode in [True, False]:
            self.header(doc)['explode'] = explode
            self.assertTrue(self.check(doc, 'ready, 2, true')['valid'])
            for value, code in [('ready,PRIVATE,true', 'schema_type'), ('ready,0,true', 'schema_minimum'),
                                ('ready,2,maybe', 'schema_type'), ('PRIVATE,2,true', 'schema_enum'),
                                ('ready,null,true', 'schema_type')]:
                result = self.check(doc, value)
                self.assertIn(code, [i['code'] for i in result['issues']])
                self.assertNotIn('PRIVATE', json.dumps(result))

    def test_prefix_length_does_not_imply_required_positions(self):
        self.assertTrue(self.check(self.spec(), 'ready')['valid'])
        self.assertIn('schema_minItems', [i['code'] for i in self.check(self.spec(minItems=3), 'ready')['issues']])
        self.assertIn('schema_items', [i['code'] for i in self.check(self.spec(), 'ready,2,true,extra')['issues']])
        self.assertTrue(self.check(self.spec(prefixItems=[{'type': 'string'}]), '')['valid'])
        result = self.check(self.spec(prefixItems=[{'type': 'integer'}]), '')
        self.assertIn('schema_type', [i['code'] for i in result['issues']])

    def test_tail_schema_true_and_default(self):
        doc = self.spec(items={'type': 'integer', 'minimum': 10}, maxItems=5)
        self.assertTrue(self.check(doc, 'ready,2,true,10,11')['valid'])
        self.assertFalse(self.check(doc, 'ready,2,true,9')['valid'])
        self.assertFalse(self.check(doc, 'ready,2,true,10,11,12')['valid'])
        doc = self.spec(items=True)
        self.assertTrue(self.check(doc, 'ready,2,true,raw')['valid'])
        del self.header(doc)['schema']['items']
        self.assertTrue(self.check(doc, 'ready,2,true,raw')['valid'])
        doc = self.spec(prefixItems=[{'type': 'integer'}], items={'type': 'integer'}, uniqueItems=True)
        self.assertIn('schema_uniqueItems', [i['code'] for i in self.check(doc, '1,01')['issues']])

    def test_unsupported_shapes_and_version_fail_safely(self):
        for prefix in [[{'type': 'object'}], [{'type': 'array', 'items': {'type': 'string'}}], [{'type': ['integer', 'string']}]]:
            result = self.check(self.spec(prefixItems=prefix), 'PRIVATE')
            self.assertIn('unsupported_header_serialization', [i['code'] for i in result['issues']])
            self.assertNotIn('PRIVATE', json.dumps(result))
        doc = self.spec(); doc['openapi'] = '3.0.3'
        doc['components']['schemas']['Count']['type'] = 'integer'
        self.assertFalse(self.check(doc, 'ready,2,true')['valid'])
        doc = self.spec(prefixItems=[{'allOf': [{'type': 'integer'}, {'minimum': 1}]}])
        self.assertTrue(self.check(doc, '2')['valid'])
        self.assertFalse(self.check(doc, '0')['valid'])

    def test_real_http_runner_tuple_contract(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                body = b'{"id":1}'
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('X-Tuple', 'ready,2,true' if self.path.endswith('/1') else 'ready,true,2')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 2); self.addCleanup(server.shutdown)
        for suffix, expected in [('1', 'passed'), ('2', 'failed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
            for composed in [None, 'allOf', 'oneOf', 'anyOf']:
                with self.subTest(expected=expected, composed=composed):
                    doc = self.spec(minItems=3)
                    if composed:
                        header = self.header(doc)
                        doc['components']['schemas']['Tuple'] = header['schema']
                        if composed == 'allOf':
                            header['schema'] = {'allOf': [{'$ref': '#/components/schemas/Tuple'}, {'minItems': 3}]}
                        else:
                            header['schema'] = {composed: [
                                {'$ref': '#/components/schemas/Tuple'},
                                {'allOf': [{'$ref': '#/components/schemas/Tuple'}, {'maxItems': 1}]}
                            ]}
                    result = ApiTestRunner().run_case('tuple-header', case, contract_document=doc)
                    self.assertEqual(result.status, expected)
                    self.assertEqual(result.contract['valid'], expected == 'passed')
