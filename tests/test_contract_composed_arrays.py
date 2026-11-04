import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
from test_contracts import document


class ComposedHeaderArrayTests(unittest.TestCase):
    def spec(self, version='3.0.3'):
        doc = document(version)
        doc['components']['schemas']['HeaderArray'] = {'type': 'array', 'items': {'type': 'integer', 'minimum': 1}}
        doc['paths']['/items/{id}']['get']['responses']['200']['headers'] = {'X-Values': {'required': True, 'schema': {
            'allOf': [{'$ref': '#/components/schemas/HeaderArray'}, {'minItems': 2, 'maxItems': 3, 'uniqueItems': True},
                      {'items': {'maximum': 5}}]}}}
        return doc

    def check(self, doc, raw):
        return validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'x-values': raw}, {'id': 1})

    def test_versions_refs_and_all_original_constraints(self):
        for version in ['3.0.3', '3.1.0']:
            doc = self.spec(version)
            self.assertTrue(self.check(doc, '1,2')['valid'])
            for value, code in [('1', 'schema_minItems'), ('1,2,3,4', 'schema_maxItems'), ('1,1', 'schema_uniqueItems'),
                                ('0,2', 'schema_minimum'), ('1,6', 'schema_maximum'), ('1,PRIVATE', 'schema_type')]:
                result = self.check(doc, value)
                self.assertIn(code, [i['code'] for i in result['issues']])
                self.assertNotIn('PRIVATE', json.dumps(result))

    def test_nested_allof_nullable_and_explode(self):
        doc = self.spec('3.1.0')
        doc['components']['schemas']['HeaderArray']['type'] = ['array', 'null']
        doc['components']['schemas']['HeaderArray']['items']['type'] = ['integer', 'null']
        header = doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Values']
        header['schema'] = {'allOf': [header['schema']]}
        for explode in [True, False]:
            header['explode'] = explode
            self.assertTrue(self.check(doc, '1,2')['valid'])
            self.assertFalse(self.check(doc, '1,null')['valid'])

    def test_items_intersection_and_direct_array_preservation(self):
        doc = self.spec()
        header = doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Values']
        header['schema'] = {'type': 'array', 'items': {'type': 'number'}, 'allOf': [{'items': {'type': 'integer', 'minimum': 2}}]}
        self.assertTrue(self.check(doc, '2,3')['valid'])
        self.assertFalse(self.check(doc, '1,2')['valid'])
        self.assertFalse(self.check(doc, '2,3.5')['valid'])
        header['schema'] = {'allOf': [{'type': 'array', 'items': {'type': 'integer'}}, {'items': {'type': 'string'}}]}
        self.assertFalse(self.check(doc, '1,2')['valid'])

    def test_unsupported_container_composition_and_bounds(self):
        for branches in [
            [{'type': 'array', 'items': {'type': 'integer'}}, {'type': 'object'}],
            [{'type': 'array', 'items': {'type': 'integer'}}, {'oneOf': [{'maxItems': 2}, {'minItems': 3}]}],
            [{'type': 'array', 'items': {'type': 'integer'}}] * 130,
        ]:
            doc = self.spec('3.1.0')
            header = doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Values']
            header['schema'] = {'allOf': branches}
            self.assertFalse(self.check(doc, '1,2')['valid'])
        doc = self.spec()
        doc['components']['schemas']['HeaderArray'] = {'allOf': [{'$ref': '#/components/schemas/HeaderArray'}]}
        self.assertFalse(self.check(doc, '1,2')['valid'])

    def test_real_http_runner_composed_array(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                body = b'{"id":1}'
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('X-Values', '1,2' if self.path.endswith('/1') else '1,1')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 2); self.addCleanup(server.shutdown)
        for suffix, expected in [('1', 'passed'), ('2', 'failed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
            result = ApiTestRunner().run_case('composed-array', case, contract_document=self.spec())
            self.assertEqual(result.status, expected)
            self.assertEqual(result.contract['valid'], expected == 'passed')
