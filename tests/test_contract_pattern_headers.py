import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
from test_contracts import document


class PatternHeaderTests(unittest.TestCase):
    def spec(self):
        doc = document('3.1.0')
        doc['components']['schemas']['Count'] = {'type': 'integer', 'minimum': 1}
        schema = {'type': 'object', 'patternProperties': {'^I_': {'$ref': '#/components/schemas/Count'}, '^S_': {'type': 'string'}}, 'additionalProperties': False}
        doc['paths']['/items/{id}']['get']['responses']['200']['headers'] = {'X-Map': {'schema': schema, 'required': True}}
        return doc

    def header(self, doc):
        return doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Map']

    def check(self, doc, raw):
        return validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'X-Map': raw}, {'id': 1})

    def test_patterns_refs_and_explode(self):
        doc = self.spec()
        self.assertTrue(self.check(doc, 'I_count,2,S_name,hello')['valid'])
        self.header(doc)['explode'] = True
        self.assertTrue(self.check(doc, 'I_count=2,S_name=123')['valid'])
        for raw in ['I_count=0', 'I_count=PRIVATE', 'unknown=PRIVATE']:
            result = self.check(doc, raw)
            self.assertFalse(result['valid'])
            self.assertNotIn('PRIVATE', json.dumps(result))

    def test_properties_and_all_matching_patterns_apply(self):
        doc = self.spec(); schema = self.header(doc)['schema']
        schema['properties'] = {'I_count': {'maximum': 5}}
        schema['patternProperties']['count'] = {'type': 'number', 'minimum': 2}
        self.assertTrue(self.check(doc, 'I_count,3')['valid'])
        self.assertFalse(self.check(doc, 'I_count,1')['valid'])
        self.assertFalse(self.check(doc, 'I_count,6')['valid'])
        self.assertTrue(self.check(doc, 'discount,2.5')['valid'])  # Patterns are not implicitly anchored.
        self.assertFalse(self.check(doc, 'xI_value,2')['valid'])
        schema['patternProperties']['count'] = {'type': 'string'}
        self.assertIn('unsupported_header_serialization', [i['code'] for i in self.check(doc, 'I_count,3')['issues']])

    def test_additional_and_boolean_patterns(self):
        doc = self.spec(); schema = self.header(doc)['schema']
        schema['additionalProperties'] = {'type': 'boolean'}
        self.assertTrue(self.check(doc, 'I_count,2,flag,true')['valid'])
        schema['patternProperties'].update({'^free': True, '^blocked': False})
        self.assertTrue(self.check(doc, 'free,123')['valid'])
        result = self.check(doc, 'blocked,PRIVATE')
        self.assertFalse(result['valid'])
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertNotIn('unsupported_header_serialization', [i['code'] for i in result['issues']])

    def test_invalid_patterns_nested_and_30_fail_safely(self):
        doc = self.spec(); self.header(doc)['schema']['patternProperties'] = {'[': {'type': 'integer'}}
        self.assertFalse(self.check(doc, 'key,1')['valid'])
        doc = self.spec(); self.header(doc)['schema']['patternProperties'] = {'^nested': {'type': 'object'}}
        self.assertFalse(self.check(doc, 'nested,value')['valid'])
        doc = self.spec(); doc['openapi'] = '3.0.3'
        self.assertFalse(self.check(doc, 'I_count,2')['valid'])

    def test_real_http_pattern_runner(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                body = b'{"id":1}'
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('X-Map', 'I_count,2' if self.path.endswith('/1') else 'I_count,0')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 2); self.addCleanup(server.shutdown)
        for suffix, expected in [('1', 'passed'), ('2', 'failed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
            result = ApiTestRunner().run_case('pattern-header', case, contract_document=self.spec())
            self.assertEqual(result.status, expected)
            self.assertEqual(result.contract['valid'], expected == 'passed')
