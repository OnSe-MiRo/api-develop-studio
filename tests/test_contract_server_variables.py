import json
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch
from api_test.contracts import ContractError, validate_response
from api_test.contracts.validation import match_operation, validate_server_variables
from api_test.services import studio
from test_contract_servers import spec


def variable_spec(version='3.0.3'):
    doc=spec(version)
    doc['paths']['/items']['get']['servers']=[{'url':'/{version}', 'variables':{'version':{'default':'v1','enum':['v1','v2']}}}]
    return doc

class ServerVariableTests(unittest.TestCase):
    def test_explicit_value_defaults_enum_and_no_project_alias_bypass(self):
        for version in ['3.0.3','3.1.0']:
            doc=variable_spec(version)
            for url,values,valid in [('/v1/items',None,True),('/v2/items',{'version':'v2'},True),('/v1/items',{'version':'v2'},False),('/v3/items',{'version':'v3'},False),('/v1/items',{'unknown':'PRIVATE'},False),('/v1/items',{},True)]:
                result=validate_response(doc,'GET',url,200,{'Content-Type':'application/json'},{'ok':True},base_url='https://test/v3',server_variables=values)
                self.assertEqual(result['valid'],valid,(url,values,result));self.assertNotIn('PRIVATE',json.dumps(result))

    def test_unused_variables_and_server_scope_do_not_poison_other_operations(self):
        doc=variable_spec()
        doc['paths']['/other']={'get':{'servers':[{'url':'/fixed'}],'responses':{'200':{'description':'ok'}}}}
        self.assertEqual(match_operation(doc,'GET','/v2/items',server_variables={'version':'v2'})[0],'/items')
        with self.assertRaises(ContractError):match_operation(doc,'GET','/fixed/other',server_variables={'version':'v2'})
        doc['paths']['/items']['get']['servers'].insert(0,{'url':'/unrelated'})
        self.assertEqual(match_operation(doc,'GET','/v2/items',server_variables={'version':'v2'})[0],'/items')
        doc['paths']['/items']['get']['servers'][1]['variables']['unused']={'default':'x'}
        with self.assertRaises(ContractError):match_operation(doc,'GET','/v1/items',server_variables={'unused':'x'})

    def test_partial_values_and_ambiguity(self):
        doc=variable_spec();server=doc['paths']['/items']['get']['servers'][0]
        server['url']='/{region}/{version}';server['variables']['region']={'default':'east'}
        self.assertEqual(match_operation(doc,'GET','/east/v2/items',server_variables={'version':'v2'})[0],'/items')
        server['variables']['version']['default']='v2'
        doc['paths']['/v2/items']=deepcopy(doc['paths']['/items']);doc['paths']['/v2/items']['get']['servers'][0]['url']='/{region}'
        with self.assertRaises(ContractError):match_operation(doc,'GET','/east/v2/items',server_variables={'region':'east'})

    def test_shape_limits_and_no_value_leak(self):
        for value in [None,[],True,{'v':1},{'':'x'},{'x'*129:'a'},{'v':'x'*513},{'v':'PRIVATE\n'},dict.fromkeys([str(i) for i in range(33)],'x')]:
            with self.assertRaises(ContractError):validate_server_variables(value)
        self.assertEqual(validate_server_variables({'x'*128:'v'*512}),{'x'*128:'v'*512})
        result=validate_response(variable_spec(),'GET','/v2/items',200,{},None,server_variables={'version':'PRIVATE#fragment'})
        self.assertFalse(result['valid']);self.assertNotIn('PRIVATE',json.dumps(result))

    def test_quick_call_invalid_input_is_rejected_before_network_and_disabled_mode(self):
        store=Mock();store.get.return_value=SimpleNamespace(document={'docs_file':{'document':variable_spec()}})
        settings=SimpleNamespace(auth_profiles={},variables={},encrypted_variables={},base_url='https://example.test')
        with patch.object(studio,'collaboration_store',return_value=store),patch.object(studio,'project_request_settings',return_value=settings),patch.object(studio,'execute_http_call') as send:
            for values in [None,[],{'version':3},{'version':'PRIVATE'},{'other':'v2'}]:
                with self.assertRaises(studio.ApiError) as error:
                    studio.handle_api_request({'url':'https://example.test/v2/items','project':'fixture.json','validateContract':True,'serverVariables':values})
                self.assertNotIn('PRIVATE',str(error.exception))
            with self.assertRaises(studio.ApiError):studio.handle_api_request({'url':'https://example.test/items','serverVariables':{}})
        send.assert_not_called()

    def test_real_http_explicit_variable_keeps_request_url(self):
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
        store=Mock();store.get.return_value=SimpleNamespace(document={'docs_file':{'document':variable_spec()}})
        settings=SimpleNamespace(auth_profiles={},variables={},encrypted_variables={},base_url=origin)
        with patch.object(studio,'collaboration_store',return_value=store),patch.object(studio,'project_request_settings',return_value=settings),patch.object(studio,'local_policy',return_value={'skip_verification':True}):
            result=studio.handle_api_request({'url':origin+'/v2/items','project':'fixture.json','validateContract':True,'serverVariables':{'version':'v2'},'no_proxy':True})
        self.assertTrue(result['contract']['valid'],result);self.assertEqual(seen,['/v2/items'])
