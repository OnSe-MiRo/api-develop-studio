import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
from test_contracts import document


class BooleanFieldTests(unittest.TestCase):
    def spec(self, free=True, forbidden=False):
        doc = document('3.1.0')
        doc['components']['schemas'].update(Free=free, Forbidden=forbidden)
        schema = {'type': 'object', 'properties': {'free': {'$ref': '#/components/schemas/Free'}, 'blocked': {'$ref': '#/components/schemas/Forbidden'}, 'id': {'type': 'integer'}}, 'required': ['id'], 'additionalProperties': False}
        doc['paths']['/items/{id}']['get']['responses']['200']['headers'] = {'X-Object': {'schema': schema, 'required': True}}
        return doc

    def header(self, doc):
        return doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Object']

    def check(self, doc, value):
        return validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'X-Object': value}, {'id': 1})

    def test_free_fields_preserve_text_and_typed_fields(self):
        for free in [True, {}]:
            doc = self.spec(free=free)
            self.header(doc)['schema']['enum'] = [{'free': '123', 'id': 2}]
            self.assertTrue(self.check(doc, 'free,123,id,2')['valid'])
            self.assertFalse(self.check(doc, 'free,123,id,3')['valid'])
            self.header(doc)['explode'] = True
            self.assertTrue(self.check(doc, 'free=123,id=2')['valid'])

    def test_false_presence_required_and_extra_constraints(self):
        doc = self.spec()
        self.assertTrue(self.check(doc, 'id,2')['valid'])
        for raw in ['id,2,blocked,PRIVATE', 'id,2,blocked,', 'id,2,extra,PRIVATE']:
            result = self.check(doc, raw)
            self.assertFalse(result['valid'])
            self.assertNotIn('unsupported_header_serialization', [i['code'] for i in result['issues']])
            self.assertNotIn('PRIVATE', json.dumps(result))
        self.header(doc)['schema']['required'].append('blocked')
        self.assertFalse(self.check(doc, 'id,2')['valid'])
        self.assertFalse(self.check(doc, 'id,2,blocked,x')['valid'])

    def test_empty_additional_schema_and_version_boundary(self):
        doc = self.spec()
        self.header(doc)['schema']['additionalProperties'] = {}
        self.assertTrue(self.check(doc, 'id,2,extra,123')['valid'])
        doc['openapi'] = '3.0.3'
        self.assertFalse(self.check(doc, 'id,2')['valid'])
        doc['components']['schemas'].update(Free={}, Forbidden={})
        self.assertTrue(self.check(doc, 'id,2,free,123')['valid'])

    def test_real_http_false_field_runner(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                body = b'{"id":1}'
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('X-Object', 'id,2,free,123' if self.path.endswith('/1') else 'id,2,blocked,PRIVATE')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 2); self.addCleanup(server.shutdown)
        for suffix, expected in [('1', 'passed'), ('2', 'failed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
            result = ApiTestRunner().run_case('boolean-field', case, contract_document=self.spec())
            self.assertEqual(result.status, expected)
            self.assertNotIn('PRIVATE', str(result.differences))
