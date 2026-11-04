import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
from test_contracts import document


class UnionHeaderArrayTests(unittest.TestCase):
    def spec(self, keyword='oneOf', version='3.0.3'):
        doc = document(version)
        doc['components']['schemas']['LowArray'] = {'type': 'array', 'items': {'type': 'integer', 'enum': [1, 2]}, 'minItems': 2}
        doc['components']['schemas']['HighArray'] = {'allOf': [{'type': 'array', 'items': {'type': 'integer', 'enum': [10, 20]}}, {'minItems': 2, 'maxItems': 3}]}
        doc['paths']['/items/{id}']['get']['responses']['200']['headers'] = {'X-Values': {'required': True, 'schema': {keyword: [
            {'$ref': '#/components/schemas/LowArray'}, {'$ref': '#/components/schemas/HighArray'}]}}}
        return doc

    def header(self, doc):
        return doc['paths']['/items/{id}']['get']['responses']['200']['headers']['X-Values']

    def check(self, doc, raw):
        return validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'x-values': raw}, {'id': 1})

    def test_versions_refs_allof_and_whole_array_constraints(self):
        for version in ['3.0.3', '3.1.0']:
            for keyword in ['oneOf', 'anyOf']:
                doc = self.spec(keyword, version)
                for raw in ['1,2', '10,20']:
                    self.assertTrue(self.check(doc, raw)['valid'])
                # Each item fits some branch, but no branch accepts the entire array.
                for raw in ['1,10', '1', '10,20,10,20', '1,PRIVATE']:
                    result = self.check(doc, raw)
                    self.assertIn('schema_' + keyword, [i['code'] for i in result['issues']])
                    self.assertNotIn('PRIVATE', json.dumps(result))

    def test_oneof_overlap_and_anyof_overlap(self):
        for keyword, expected in [('oneOf', False), ('anyOf', True)]:
            doc = self.spec(keyword)
            self.header(doc)['schema'] = {keyword: [
                {'type': 'array', 'items': {'type': 'integer'}, 'minItems': 1},
                {'type': 'array', 'items': {'type': 'integer'}, 'maxItems': 3}]}
            self.assertEqual(self.check(doc, '1,2')['valid'], expected)

    def test_nested_union_nullable_and_explode(self):
        doc = self.spec('anyOf', '3.1.0')
        doc['components']['schemas']['LowArray']['type'] = ['array', 'null']
        doc['components']['schemas']['LowArray']['items']['type'] = ['integer', 'null']
        inner = self.header(doc)['schema']
        self.header(doc)['schema'] = {'oneOf': [inner, {'type': 'array', 'items': {'type': 'integer', 'enum': [100]}, 'minItems': 1}]}
        for explode in [True, False]:
            self.header(doc)['explode'] = explode
            self.assertTrue(self.check(doc, '1,2')['valid'])
            self.assertTrue(self.check(doc, '100')['valid'])
            self.assertFalse(self.check(doc, '1,null')['valid'])

    def test_mixed_nonarray_untyped_cycles_and_limits_are_not_inferred(self):
        base = {'type': 'array', 'items': {'type': 'integer'}}
        for other in [{'type': 'array', 'items': {'type': 'string'}}, {'type': 'object'}, {'type': 'array'}, {}]:
            doc = self.spec(version='3.1.0')
            self.header(doc)['schema'] = {'anyOf': [base, other]}
            # A mismatched string body cannot satisfy these schemas except the untyped branch.
            if other != {}:
                self.assertFalse(self.check(doc, '1,2')['valid'])
            else:
                # Existing scalar fallback stays a string; it must not invent array decoding.
                doc['components']['schemas']['HighArray'] = {}
                self.header(doc)['schema']['type'] = 'array'
                self.assertFalse(self.check(doc, '1,2')['valid'])
        doc = self.spec()
        self.header(doc)['schema'] = {'oneOf': [base] * 130}
        self.assertFalse(self.check(doc, '1,2')['valid'])
        doc['components']['schemas']['Loop'] = {'anyOf': [base, {'$ref': '#/components/schemas/Loop'}]}
        self.header(doc)['schema'] = {'anyOf': [{'$ref': '#/components/schemas/Loop'}]}
        self.assertFalse(self.check(doc, '1,2')['valid'])

    def test_real_http_runner_union_array(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                body = b'{"id":1}'
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('X-Values', '1,2' if self.path.endswith('/1') else '1,10')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 2); self.addCleanup(server.shutdown)
        for suffix, expected in [('1', 'passed'), ('2', 'failed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
            result = ApiTestRunner().run_case('union-array', case, contract_document=self.spec())
            self.assertEqual(result.status, expected)
            self.assertEqual(result.contract['valid'], expected == 'passed')
