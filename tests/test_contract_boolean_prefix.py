import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
import test_contract_prefix_headers as prefix_fixture


class BooleanPrefixTests(unittest.TestCase):
    def check(self, doc, raw):
        return prefix_fixture.PrefixHeaderTests().check(doc, raw)

    def test_true_and_empty_schema_keep_strings_with_typed_positions(self):
        for permissive in [True, {}]:
            doc = prefix_fixture.PrefixHeaderTests().spec(prefixItems=[permissive, {'type': 'integer'}], minItems=2, enum=[['123', 2]])
            self.assertTrue(self.check(doc, '123,2')['valid'])
            self.assertFalse(self.check(doc, '123,3')['valid'])
            self.assertFalse(self.check(doc, '123,2,extra')['valid'])
            doc = prefix_fixture.PrefixHeaderTests().spec(prefixItems=[permissive], items={})
            self.assertTrue(self.check(doc, '')['valid'])
            self.assertTrue(self.check(doc, 'true,123')['valid'])

    def test_false_only_rejects_a_present_position(self):
        doc = prefix_fixture.PrefixHeaderTests().spec(prefixItems=[{'const': 'ready'}, False])
        self.assertTrue(self.check(doc, 'ready')['valid'])
        for raw in ['ready,PRIVATE', 'ready,']:
            result = self.check(doc, raw)
            self.assertFalse(result['valid'])
            self.assertNotIn('unsupported_header_serialization', [i['code'] for i in result['issues']])
            self.assertNotIn('PRIVATE', json.dumps(result))
        prefix_fixture.PrefixHeaderTests().header(doc)['schema']['minItems'] = 2
        self.assertFalse(self.check(doc, 'ready')['valid'])

    def test_referenced_boolean_and_30_rejection(self):
        doc = prefix_fixture.PrefixHeaderTests().spec(prefixItems=[{'$ref': '#/components/schemas/Any'}, {'$ref': '#/components/schemas/Never'}])
        doc['components']['schemas'].update(Any=True, Never=False)
        self.assertTrue(self.check(doc, '123')['valid'])
        self.assertFalse(self.check(doc, '123,anything')['valid'])
        doc['openapi'] = '3.0.3'
        self.assertFalse(self.check(doc, '123')['valid'])

    def test_real_http_false_position_runner(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                body = b'{"id":1}'
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('X-Tuple', 'ready' if self.path.endswith('/1') else 'ready,PRIVATE')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 2); self.addCleanup(server.shutdown)
        doc = prefix_fixture.PrefixHeaderTests().spec(prefixItems=[{'const': 'ready'}, False])
        for suffix, expected in [('1', 'passed'), ('2', 'failed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
            result = ApiTestRunner().run_case('boolean-prefix', case, contract_document=doc)
            self.assertEqual(result.status, expected)
            self.assertNotIn('PRIVATE', str(result.differences))
