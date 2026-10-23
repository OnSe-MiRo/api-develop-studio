import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from api_test.contracts import ContractError, validate_response
from api_test.contracts.validation import match_operation, validate_document_url
from api_test.services import studio
from test_contract_servers import spec


def relative_spec(version='3.0.3', server='../{version}'):
    doc=spec(version)
    doc['paths']['/items']['get']['servers']=[{'url':server,'variables':{'version':{'default':'v1','enum':['v1','v2']}}}]
    return doc

class RelativeServerTests(unittest.TestCase):
    def test_relative_paths_are_resolved_against_document_location(self):
        base='https://docs.test/service/spec/openapi.json'
        for version in ['3.0.3','3.1.0']:
            for server,path in [('v2','/service/spec/v2/items'),('./v2','/service/spec/v2/items'),('../v2','/service/v2/items'),('../../v2','/v2/items'),('/v2','/v2/items'),('https://other.test/v2','/v2/items'),('//other.test/v2','/v2/items')]:
                with self.subTest(version=version,server=server):
                    result=validate_response(relative_spec(version,server),'GET','https://api.test'+path,200,{'Content-Type':'application/json'},{'ok':True},document_url=base)
                    self.assertTrue(result['valid'],result)

    def test_default_and_explicit_values_expand_before_resolution(self):
        base='https://docs.test/service/spec/openapi.json';doc=relative_spec()
        self.assertEqual(match_operation(doc,'GET','/service/v1/items',document_url=base)[0],'/items')
        self.assertEqual(match_operation(doc,'GET','/service/v2/items',server_variables={'version':'v2'},document_url=base)[0],'/items')
        with self.assertRaises(ContractError):match_operation(doc,'GET','/service/v2/items',document_url=base)
        with self.assertRaises(ContractError):match_operation(doc,'GET','/service/v1/items')

    def test_trailing_slash_document_location_is_significant(self):
        doc=relative_spec(server='v2')
        self.assertEqual(match_operation(doc,'GET','/service/v2/items',document_url='https://test/service/openapi.json')[0],'/items')
        self.assertEqual(match_operation(doc,'GET','/service/openapi.json/v2/items',document_url='https://test/service/openapi.json/')[0],'/items')
        with self.assertRaises(ContractError):match_operation(doc,'GET','/service/v2/items',document_url='https://test/service/openapi.json/')

    def test_scope_and_project_alias_cannot_override_explicit_document_base(self):
        doc=relative_spec();doc['servers']=[{'url':'/root'}];doc['paths']['/items']['servers']=[{'url':'/path'}]
        base='https://docs.test/service/spec/openapi.json'
        for url in ['/root/items','/path/items','/wrong/items','/service/v10/items']:
            with self.assertRaises(ContractError):match_operation(doc,'GET',url,base_url='https://api.test/wrong',document_url=base)
        doc=spec();doc['servers']=[{'url':'v1'}]
        with self.assertRaises(ContractError):match_operation(doc,'GET','/wrong/items',base_url='https://api.test/wrong',document_url=base)
        self.assertEqual(match_operation(doc,'GET','/service/spec/v1/items',document_url=base)[0],'/items')

    def test_invalid_locations_do_not_leak_input_or_trigger_network(self):
        invalid=[None,True,{},'','file:///PRIVATE','/PRIVATE','https://user:PRIVATE@test/spec','https://test/spec?PRIVATE=1','https://test/spec#PRIVATE','https://test:bad/spec','https://test/white space','https://test/\\PRIVATE','https://test/'+('x'*2048)]
        with patch.object(studio,'execute_http_call') as send:
            for value in invalid:
                with self.subTest(value=type(value).__name__):
                    with self.assertRaises(ContractError):validate_document_url(value)
                    with self.assertRaises(studio.ApiError) as error:studio.handle_api_request({'url':'https://test/items','validateContract':True,'contractDocumentUrl':value})
                    self.assertNotIn('PRIVATE',str(error.exception))
            with self.assertRaises(studio.ApiError):studio.handle_api_request({'url':'https://test/items','contractDocumentUrl':'https://docs.test/spec'})
        send.assert_not_called()
        result=validate_response(relative_spec(),'GET','/v1/items',200,{},None,document_url='https://user:PRIVATE@test/spec')
        self.assertFalse(result['valid']);self.assertNotIn('PRIVATE',json.dumps(result))

    def test_real_http_only_calls_target_and_never_fetches_document_hint(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from threading import Thread
        seen=[]
        class Target(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                seen.append(self.path);body=b'{"ok":true}'
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Target);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(thread.join,2);self.addCleanup(server.shutdown)
        origin=f'http://127.0.0.1:{server.server_port}'
        store=Mock();store.get.return_value=SimpleNamespace(document={'docs_file':{'document':relative_spec()}})
        settings=SimpleNamespace(auth_profiles={},variables={},encrypted_variables={},base_url=origin)
        with patch.object(studio,'collaboration_store',return_value=store),patch.object(studio,'project_request_settings',return_value=settings),patch.object(studio,'local_policy',return_value={'skip_verification':True}):
            result=studio.handle_api_request({'project':'fixture.json','url':origin+'/service/v2/items','validateContract':True,'serverVariables':{'version':'v2'},'contractDocumentUrl':origin+'/service/spec/openapi.json','no_proxy':True})
            with self.assertRaises(studio.ApiError):studio.handle_api_request({'project':'fixture.json','url':origin+'/service/v2/items','validateContract':True,'serverVariables':{'version':'v2'},'contractDocumentUrl':origin+'/wrong/spec/openapi.json','no_proxy':True})
        self.assertTrue(result['contract']['valid'],result);self.assertEqual(seen,['/service/v2/items'])
