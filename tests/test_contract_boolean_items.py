import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
from test_contracts import document


class BooleanItemsTests(unittest.TestCase):
    def spec(self, items=True):
        doc = document('3.1.0')
        doc['components']['schemas']['AnyItem'] = items
        doc['paths']['/items/{id}']['get']['responses']['200']['headers'] = {'X-Array': {'required': True, 'schema': {'type': 'array', 'items': {'$ref': '#/components/schemas/AnyItem'}}}}
        return doc

    def header(self, doc):
        return doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Array']

    def check(self, doc, value):
        return validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'X-Array': value}, {'id': 1})

    def test_true_empty_and_omitted_items_preserve_text(self):
        for items in [True, {}]:
            doc = self.spec(items)
            self.header(doc)['schema']['enum'] = [['1', 'true', 'null', '']]
            for explode in [True, False]:
                self.header(doc)['explode'] = explode
                self.assertTrue(self.check(doc, '1,true,null,')['valid'])
        doc = self.spec(); del self.header(doc)['schema']['items']
        self.header(doc)['schema']['enum'] = [['123']]
        self.assertTrue(self.check(doc, '123')['valid'])

    def test_false_items_reject_present_values_but_optional_header_can_be_absent(self):
        doc = self.spec(False)
        for raw in ['', 'PRIVATE', '1,2']:
            result = self.check(doc, raw)
            self.assertFalse(result['valid'])
            self.assertNotIn('unsupported_header_serialization', [i['code'] for i in result['issues']])
            self.assertNotIn('PRIVATE', json.dumps(result))
        self.header(doc)['required'] = False
        self.assertTrue(validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json'}, {'id': 1})['valid'])

    def test_original_constraints_and_30_boundary(self):
        doc = self.spec({}); self.header(doc)['schema'].update(minItems=2, maxItems=2, uniqueItems=True)
        self.assertTrue(self.check(doc, 'a,b')['valid'])
        for raw, code in [('a', 'schema_minItems'), ('a,b,c', 'schema_maxItems'), ('a,a', 'schema_uniqueItems')]:
            self.assertIn(code, [i['code'] for i in self.check(doc, raw)['issues']])
        doc['openapi'] = '3.0.3'
        self.assertTrue(self.check(doc, 'a,b')['valid'])
        doc['components']['schemas']['AnyItem'] = True
        self.assertFalse(self.check(doc, 'a,b')['valid'])

    def test_real_http_unconstrained_array_runner(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                body = b'{"id":1}'
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('X-Array', 'a,b' if self.path.endswith('/1') else 'a,a')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 2); self.addCleanup(server.shutdown)
        doc = self.spec(); self.header(doc)['schema']['uniqueItems'] = True
        for suffix, expected in [('1', 'passed'), ('2', 'failed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
            result = ApiTestRunner().run_case('boolean-items', case, contract_document=doc)
            self.assertEqual(result.status, expected)
