import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from api_test.contracts import validate_response
from api_test.runner import ApiTestRunner
from api_test.reports import RunReport, now
from test_contracts import document


class TextHeaderTests(unittest.TestCase):
    def spec(self, schema, version='3.0.3', media='text/plain'):
        doc = document(version)
        doc['components']['schemas']['TextHeader'] = schema
        doc['components']['headers'] = {'TextHeader': {'required': True, 'content': {media: {'schema': {'$ref': '#/components/schemas/TextHeader'}}}}}
        doc['paths']['/items/{id}']['get']['responses']['200']['headers'] = {'X-Text': {'$ref': '#/components/headers/TextHeader'}}
        return doc

    def check(self, doc, value):
        return validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json', 'x-text': value}, {'id': 1})

    def test_raw_text_is_preserved_in_both_versions(self):
        for version in ['3.0.3', '3.1.0']:
            for media in ['text/plain', 'Text/Plain; charset=utf-8']:
                for value in ['', '  a,b=c  ', '{"id":1}', '123', 'true', '한글', 'a%2Cb']:
                    with self.subTest(version=version, media=media, value=value):
                        result = self.check(self.spec({'type': 'string', 'enum': [value]}, version, media), value)
                        self.assertTrue(result['valid'], result)
                for kind, value in [('integer', '123'), ('boolean', 'true'), ('object', '{"id":1}')]:
                    result = self.check(self.spec({'type': kind}, version, media), value)
                    self.assertIn('schema_type', [i['code'] for i in result['issues']])

    def test_constraints_missing_and_optional(self):
        for version in ['3.0.3', '3.1.0']:
            for schema, value, code in [
                ({'type': 'string', 'minLength': 1}, '', 'schema_minLength'),
                ({'type': 'string', 'maxLength': 2}, 'PRIVATE', 'schema_maxLength'),
                ({'type': 'string', 'pattern': '^ok$'}, 'PRIVATE', 'schema_pattern'),
                ({'type': 'string', 'enum': ['ok']}, 'PRIVATE', 'schema_enum'),
                ({'type': 'string', 'format': 'uuid'}, 'PRIVATE', 'schema_format'),
            ]:
                result = self.check(self.spec(schema, version), value)
                self.assertIn(code, [i['code'] for i in result['issues']])
                self.assertNotIn('PRIVATE', json.dumps(result))
            doc = self.spec({'type': 'string'}, version)
            result = validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json'}, {'id': 1})
            self.assertIn('missing_header', [i['code'] for i in result['issues']])
            doc['components']['headers']['TextHeader']['required'] = False
            self.assertTrue(validate_response(doc, 'GET', '/items/1', 200, {'Content-Type': 'application/json'}, {'id': 1})['valid'])

    def test_schema_free_text_and_unsupported_media(self):
        doc = self.spec({'type': 'string'})
        del doc['components']['headers']['TextHeader']['content']['text/plain']['schema']
        self.assertTrue(self.check(doc, 'not json')['valid'])
        for media in ['text/*', '*/*', 'text/html', 'application/xml', 'application/octet-stream']:
            result = self.check(self.spec({'type': 'string'}, media=media), 'PRIVATE')
            self.assertIn('unsupported_header_content', [i['code'] for i in result['issues']])
            self.assertNotIn('PRIVATE', json.dumps(result))

    def test_real_http_runner_contract_and_report(self):
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                body = b'{"id":1}'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('X-Text', 'ready' if self.path.endswith('/1') else 'PRIVATE')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Target)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 2); self.addCleanup(server.shutdown)
        for suffix, expected in [('1', 'passed'), ('2', 'failed')]:
            case = {'project': 'demo.json', 'request': {'method': 'GET', 'url': f'http://127.0.0.1:{server.server_port}/items/{suffix}'}, 'expected': {'status': 200}, 'contract_validation': {'enabled': True}}
            result = ApiTestRunner().run_case('text-header', case, contract_document=self.spec({'type': 'string', 'enum': ['ready']}))
            self.assertEqual(result.status, expected)
            report = RunReport(); report.add(result, 'tag/api/header.json', now(), case_reference='tag/api/header.json'); report.finish(0 if expected == 'passed' else 1)
            self.assertNotIn('PRIVATE', json.dumps(report.data))
            if expected == 'failed': self.assertEqual(report.data['targets'][0]['errorCategory'], 'contract_failed')
