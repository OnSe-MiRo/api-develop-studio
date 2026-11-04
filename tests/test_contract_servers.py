from copy import deepcopy
import json
import unittest
from api_test.contracts import validate_response
from api_test.contracts.validation import match_operation
from api_test.contracts.documents import ContractError


def spec(version='3.0.3'):
    return {'openapi':version,'info':{'title':'Server fixture','version':'1'},'servers':[{'url':'https://root.test/root'}], 'paths':{'/items':{'get':{'operationId':'items','summary':'Items','responses':{'200':{'description':'ok','content':{'application/json':{'schema':{'type':'object','required':['ok'],'properties':{'ok':{'type':'boolean'}}}}}}}}}}}


def check(doc,url,**kwargs):
    return validate_response(doc,'GET',url,200,{'Content-Type':'application/json'},{'ok':True},**kwargs)


class ServerMatchingTests(unittest.TestCase):
    def test_operation_path_root_precedence_for_both_versions(self):
        for version in ['3.0.3','3.1.0']:
            doc=spec(version)
            self.assertTrue(check(doc,'https://root.test/root/items')['valid'])
            doc['paths']['/items']['servers']=[{'url':'/path'}]
            self.assertTrue(check(doc,'https://root.test/path/items')['valid'])
            self.assertFalse(check(doc,'https://root.test/root/items',base_url='https://root.test/root')['valid'])
            doc['paths']['/items']['get']['servers']=[{'url':'/operation'}]
            self.assertTrue(check(doc,'https://root.test/operation/items')['valid'])
            for wrong in ['/root/items','/path/items','/items','/operation2/items']:
                self.assertFalse(check(doc,'https://root.test'+wrong,base_url='https://root.test/root')['valid'])

    def test_server_variable_defaults_and_multiple_servers(self):
        for version in ['3.0.3','3.1.0']:
            doc=spec(version)
            doc['servers']=[{'url':'https://{host}:{port}/{version}', 'variables':{'host':{'default':'api.test'},'port':{'default':'443'},'version':{'default':'v2','enum':['v1','v2']}}}, {'url':'/alternate/'}]
            for url in ['https://api.test/v2/items?x=1','https://api.test/alternate/items']:
                self.assertTrue(check(doc,url)['valid'])
            self.assertFalse(check(doc,'https://api.test/v1/items')['valid'])

    def test_defaults_expand_before_url_parsing_without_value_leaks(self):
        doc=spec();doc['paths']['/items']['get']['servers']=[{'url':'/{secret}', 'variables':{'secret':{'default':'PRIVATE/segment'}}}]
        self.assertTrue(check(doc,'https://api.test/PRIVATE/segment/items')['valid'])
        result=check(doc,'https://api.test/wrong/items')
        self.assertFalse(result['valid']);self.assertNotIn('PRIVATE',json.dumps(result))

    def test_empty_override_uses_root_path_not_inherited_server(self):
        doc=spec();doc['paths']['/items']['servers']=[]
        self.assertTrue(check(doc,'https://api.test/items')['valid'])
        self.assertFalse(check(doc,'https://api.test/root/items')['valid'])
        doc['paths']['/items']['servers']=[{'url':'/path'}];doc['paths']['/items']['get']['servers']=[]
        self.assertTrue(check(doc,'https://api.test/items')['valid'])
        self.assertFalse(check(doc,'https://api.test/path/items')['valid'])

    def test_legacy_project_base_alias_and_no_server_documents(self):
        doc=spec();doc.pop('servers')
        self.assertTrue(check(doc,'https://dev.test/api/items',base_url='https://dev.test/api')['valid'])
        self.assertTrue(check(doc,'/items')['valid'])
        self.assertFalse(check(doc,'/api-other/items',base_url='https://dev.test/api')['valid'])

    def test_server_prefix_is_scoped_per_operation_and_ambiguity_is_rejected(self):
        doc=spec();original=doc['paths']['/items']
        original['get']['servers']=[{'url':'/v1'}]
        doc['paths']['/v1/items']=deepcopy(original);doc['paths']['/v1/items']['get']['servers']=[{'url':'/v2'}];doc['paths']['/v1/items']['get']['operationId']='other'
        self.assertEqual(match_operation(doc,'get','https://test/v1/items')[0],'/items')
        doc['paths']['/v1/items']['get']['servers']=[{'url':'/'}]
        with self.assertRaises(ContractError):match_operation(doc,'get','https://test/v1/items')

    def test_concrete_path_precedes_template_with_server_override(self):
        doc=spec();doc['paths']['/items/{id}']=deepcopy(doc['paths']['/items']);doc['paths']['/items/static']=deepcopy(doc['paths']['/items'])
        doc['paths']['/items/{id}']['get']['servers']=[{'url':'/v2'}];doc['paths']['/items/static']['get']['servers']=[{'url':'/v2'}]
        self.assertEqual(match_operation(doc,'GET','/v2/items/static')[0],'/items/static')

    def test_unsupported_relative_and_undefined_variables_fail_closed(self):
        for url in ['relative/v2','/{missing}','https://[bad/secret','/v2?token=PRIVATE','/v2#PRIVATE']:
            doc=spec();doc['paths']['/items']['get']['servers']=[{'url':url}]
            result=check(doc,'https://test/v2/items')
            self.assertFalse(result['valid']);self.assertNotIn('PRIVATE',json.dumps(result))

class RealHttpServerMatchingTests(unittest.TestCase):
    def test_quick_call_uses_override_and_validates_actual_response(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from api_test.services import studio
        seen=[]
        class Target(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                seen.append(self.path)
                payload=b'{"ok":true}'
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        server=ThreadingHTTPServer(('127.0.0.1',0),Target)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(thread.join,2);self.addCleanup(server.shutdown)
        origin=f'http://127.0.0.1:{server.server_port}'
        doc=spec();doc['paths']['/items']['get']['servers']=[{'url':'/{version}', 'variables':{'version':{'default':'operation'}}}]
        store=Mock();store.get.return_value=SimpleNamespace(document={'docs_file':{'document':doc}})
        settings=SimpleNamespace(auth_profiles={},variables={},encrypted_variables={},base_url=origin+'/root')
        with patch.object(studio,'collaboration_store',return_value=store),patch.object(studio,'project_request_settings',return_value=settings),patch.object(studio,'local_policy',return_value={'skip_verification':True}):
            good=studio.handle_api_request({'project':'fixture.json','url':origin+'/operation/items','validateContract':True,'no_proxy':True})
            bad=studio.handle_api_request({'project':'fixture.json','url':origin+'/root/items','validateContract':True,'no_proxy':True})
        self.assertEqual(good['status'],200);self.assertTrue(good['contract']['valid'],good)
        self.assertEqual(bad['status'],200);self.assertFalse(bad['contract']['valid'])
        self.assertEqual(seen,['/operation/items','/root/items'])
