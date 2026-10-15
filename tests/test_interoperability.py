import os
import json
import shlex
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from api_test.interoperability import ImportError, parse_import, export_curl
from api_test.collaboration_store import CollaborationStore
from api_test.main import app
from api_test.services import studio


class ConversionTest(unittest.TestCase):
    def test_curl_json_query_duplicates_and_quotes(self):
        command = '''curl -XPOST 'https://example.test/items?q=a%20b&q=c' -H 'Content-Type: application/json' --data-raw '{"title":"O\u0027Brien", "count":2}' '''.replace("O'Brien", "O\\u0027Brien")
        result=parse_import('curl', command)
        request=result['items'][0]['request']
        self.assertEqual(request['method'],'POST')
        self.assertEqual(request['url'],'https://example.test/items?q=a%20b&q=c')
        self.assertEqual(parse_import('curl',export_curl(request)['curl'])['items'][0]['request'],request)

    def test_curl_rejects_file_and_shell_options_without_execution(self):
        for source in ["curl https://example.test -d @/etc/passwd", "curl -K config", "curl https://example.test; echo bad", "curl https://example.test && touch file", "curl --next https://example.test", "curl https://a.test https://b.test", "curl -H 'X: one' -H 'x: two' https://example.test"]:
            with self.subTest(source=source), self.assertRaises(ImportError): parse_import('curl',source)

    def test_sensitive_values_are_removed_recursively(self):
        request={'method':'POST','url':'https://u:p@example.test/?api_key=url-secret&normal=ok','headers':{'Authorization':'Bearer header-secret','Cookie':'cookie-secret'},'body':{'password':'body-secret','nested':[{'access_token':'nested-secret','label':'kept'}]}}
        output=export_curl(request)
        for secret in ['url-secret','header-secret','cookie-secret','body-secret','nested-secret','u:p@']:
            self.assertNotIn(secret,json.dumps(output))
        self.assertIn('kept',output['curl'])
        self.assertTrue(output['warnings'])

    def test_postman_folders_disabled_fields_and_variable_mapping(self):
        document={'info':{'schema':'https://schema.getpostman.com/json/collection/v2.1.0/collection.json'},'event':[{'script':{'exec':['throw 1']}}], 'item':[{'name':'folder','item':[{'name':'create','request':{'method':'POST','url':{'raw':'{{base}}/items?off=1','query':[{'key':'q','value':'{{query}}'},{'key':'off','value':'1','disabled':True}]},'header':[{'key':'X-Ignored','value':'gone','disabled':True}],'body':{'mode':'raw','raw':'{"label":"{{label}}","password":"SECRET"}','options':{'raw':{'language':'json'}}}}}]}]}
        result=parse_import('postman',json.dumps(document)); request=result['items'][0]['request']
        self.assertEqual(request['url'],'{{project.base}}/items?q={{project.query}}')
        self.assertNotIn('SECRET',json.dumps(result)); self.assertNotIn('off=',request['url'])
        self.assertIn('{{project.label}}',request['text']); self.assertTrue(result['warnings'])

    def test_har_preserves_query_and_form_but_excludes_response_and_cookies(self):
        document={'log':{'entries':[{'request':{'method':'POST','url':'https://example.test?q=a&q=b','headers':[],'cookies':[{'name':'session','value':'COOKIE'}],'postData':{'mimeType':'application/x-www-form-urlencoded','text':'a=1&a=2&password=SECRET'}},'response':{'content':{'text':'RESPONSE'}}}]}}
        result=parse_import('har',json.dumps(document)); encoded=json.dumps(result)
        for secret in ('COOKIE','SECRET','RESPONSE'): self.assertNotIn(secret,encoded)
        self.assertIn('a=1&a=2',result['items'][0]['request']['text'])

    def test_environment_filters_explicit_secret_disabled_and_sensitive_names(self):
        result=parse_import('environment',json.dumps({'name':'dev','values':[{'key':'base','value':'https://example.test'},{'key':'password','value':'SECRET'},{'key':'custom','value':'HIDDEN','type':'secret'},{'key':'off','value':'OFF','enabled':False}]}))
        self.assertEqual(result['environment']['variables']['plain'],{'base':'https://example.test'})
        self.assertNotIn('SECRET',json.dumps(result)); self.assertNotIn('HIDDEN',json.dumps(result))

    def test_multipart_literal_values_round_trip_without_file_access(self):
        original={'method':'POST','url':'https://example.test','headers':{},'form_data':[{'key':'note','value':'@private.txt'},{'key':'tag','value':'one'},{'key':'tag','value':'two'}]}
        exported=export_curl(original)
        self.assertIn('--form-string',exported['curl'])
        self.assertEqual(parse_import('curl',exported['curl'])['items'][0]['request'],original)

    def test_generated_dtos_validate_limits(self):
        from api_test.generated.models.import_request import ImportRequest
        from pydantic import ValidationError
        self.assertEqual(ImportRequest(project='demo.json',format='curl',source='curl https://example.test').format,'curl')
        with self.assertRaises(ValidationError): ImportRequest(project='demo.json',format='curl',source='x',index=-1)

    def test_bounds_and_malformed_payloads(self):
        for format,source in [('curl','x'*(1024*1024+1)),('har','[]'),('postman','{}'),('environment','{"values":[{"key":"bad.name","value":"x"}]}'),('curl','curl file:///etc/passwd'),('curl','curl "https://example.test" -H "X: one\nInjected: two"')]:
            with self.subTest(format=format), self.assertRaises(ImportError): parse_import(format,source)

    def test_raw_text_is_explicitly_omitted_and_json_null_is_preserved(self):
        result=parse_import('curl',"curl https://example.test -H 'Content-Type: text/plain' --data-raw 'opaque secret'")
        self.assertEqual(result['items'][0]['request']['text'],''); self.assertTrue(result['warnings'])
        result=parse_import('curl',"curl https://example.test -H 'Content-Type: application/json' --data-raw null")
        self.assertEqual(result['items'][0]['request']['text'],'null')

    def test_live_echo_receives_same_request_from_exported_curl(self):
        observed=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                observed.append((self.command,self.path,self.headers.get('Content-Type'),self.headers.get('X-Label'),self.rfile.read(int(self.headers.get('Content-Length',0)))))
                self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
            def log_message(self,*args): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            original=['curl','--disable','--silent','--request','POST','--url',f'http://127.0.0.1:{server.server_port}/items?q=a%20b&q=c','--header','Content-Type: application/json','--header',"X-Label: O'Brien",'--data-raw','{"title":"hello", "count":2}']
            subprocess.run(original,check=True,capture_output=True,timeout=5)
            imported=parse_import('curl',shlex.join(original))['items'][0]['request']
            exported=export_curl(imported)['curl']
            subprocess.run(shlex.split(exported),check=True,capture_output=True,timeout=5)
            self.assertEqual(len(observed),2);self.assertEqual(observed[0],observed[1])
        finally:
            server.shutdown();server.server_close();thread.join()


class ImportHTTPTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        roots={kind:self.root/kind for kind in ('projects','cases','pipelines')}
        for path in roots.values():path.mkdir()
        self.enterContext(patch.dict(os.environ, {'STUDIO_DB_PATH':str(self.root/'studio.db'),'STUDIO_DATABASE_URL':'','STUDIO_DATABASE_URL_FILE':'','STUDIO_AUTH_MODE':'local'}))
        self.store=CollaborationStore(self.root/'studio.db',roots);self.store.initialize()
        self.store.save('projects','demo.json',{'name':'Demo','base_url':'https://example.test'})
        patches=[patch.object(studio,'collaboration_store',return_value=self.store),patch.object(studio,'PROJECT_ROOT',roots['projects']),patch.object(studio,'CASE_ROOT',roots['cases']),patch.object(studio,'PIPELINE_ROOT',roots['pipelines']),patch.object(studio,'ROOT',self.root)]
        for item in patches:item.start();self.addCleanup(item.stop)
        self.client=TestClient(app,base_url="http://127.0.0.1:8765");self.addCleanup(self.client.close)
        self.body={'project':'demo.json','format':'curl','source':"curl https://example.test/hello -H 'Authorization: SECRET'"}

    def preview(self,body=None):
        response=self.client.post('/api/interoperability/preview',json=body or self.body)
        self.assertEqual(response.status_code,200,response.text);return response.json()

    def apply(self,item,**extra):
        return self.client.post('/api/interoperability/apply',json={**self.body,'index':item.get('index'),'digest':item['digest'],**extra})

    def test_preview_does_not_write_then_apply_persists_sanitized_case(self):
        result=self.preview(); self.assertEqual(self.store.list_references('cases'),[])
        self.assertNotIn('SECRET',json.dumps(result))
        item=result['items'][0];response=self.apply(item)
        self.assertEqual(response.status_code,200,response.text)
        self.assertRegex(item['reference'],r'^imported/curl-request-[a-f0-9]{8}-1/curl.json$')
        self.assertNotIn('SECRET',json.dumps(self.store.get('cases',item['reference']).document))
        exported=self.client.post('/api/interoperability/curl',json={'reference':item['reference']})
        self.assertEqual(exported.status_code,200,exported.text);self.assertIn('curl',exported.json())

    def test_stale_preview_and_unconfirmed_overwrite_are_conflicts(self):
        first=self.preview()['items'][0]
        self.assertEqual(self.apply(first).status_code,200)
        self.assertEqual(self.apply(first).status_code,409)
        collision=self.preview()['items'][0];self.assertTrue(collision['conflict'])
        self.assertEqual(self.apply(collision).status_code,409)
        self.assertEqual(self.apply(collision,overwrite=True).status_code,200)

    def test_source_change_and_project_change_invalidate_preview(self):
        first=self.preview()['items'][0]
        self.assertEqual(self.apply(first,source='curl https://example.test/different').status_code,409)
        project=self.store.get('projects','demo.json')
        self.store.save('projects','demo.json',{**project.document,'name':'Changed'},expected_revision=project.revision)
        self.assertEqual(self.apply(first).status_code,409)
        self.assertEqual(self.store.list_references('cases'),[])

    def test_project_paths_are_isolated_and_new_tag_creates_a_second_import(self):
        original=self.preview()['items'][0]
        self.store.save('projects','second.json',{'name':'Second','base_url':'https://example.test'})
        other=self.preview({**self.body,'project':'second.json'})['items'][0]
        self.assertNotEqual(original['reference'],other['reference'])
        self.assertEqual(self.apply(original).status_code,200)
        another=self.preview({**self.body,'tag':'second-batch'})['items'][0]
        self.assertFalse(another['conflict'])
        self.assertEqual(self.apply(another,tag='second-batch').status_code,200)
        self.assertEqual(len(self.store.list_references('cases')),2)

    def test_other_project_collision_is_never_overwritten(self):
        item=self.preview()['items'][0]
        self.store.save('cases',item['reference'],{**item['document'],'project':'other.json'})
        current=self.preview()['items'][0];self.assertTrue(current['blocked'])
        self.assertEqual(self.apply(current,overwrite=True).status_code,409)

    def test_environment_preserves_existing_secret_and_default_selection(self):
        project=self.store.get('projects','demo.json')
        self.store.save('projects','demo.json',{**project.document,'default_environment':'dev','environments':{'dev':{'base_url':'https://dev.test','variables':{'plain':{'keep':'old'},'secret':{'password':'OPAQUE_ENCRYPTED'}}}}},expected_revision=project.revision)
        self.body={'project':'demo.json','format':'environment','source':json.dumps({'name':'dev','values':[{'key':'new','value':'value'},{'key':'password','value':'SECRET'}]})}
        result=self.preview(); self.assertNotIn('OPAQUE_ENCRYPTED',json.dumps(result));self.assertNotIn('SECRET',json.dumps(result))
        self.assertEqual(self.apply(result['environment'],overwrite=True).status_code,200)
        saved=self.store.get('projects','demo.json').document
        self.assertEqual(saved['default_environment'],'dev')
        self.assertEqual(saved['environments']['dev']['variables'],{'plain':{'keep':'old','new':'value'},'secret':{'password':'OPAQUE_ENCRYPTED'}})

    def test_relative_export_uses_named_base_and_default_environment(self):
        project=self.store.get('projects','demo.json')
        updated={**project.document,'base_urls':[{'name':'alternate','url':'https://alternate.test/api'}],'environments':{'dev':{'base_url':'https://dev.test/v2'}}}
        saved=self.store.save('projects','demo.json',updated,expected_revision=project.revision)
        self.store.save('cases','tag/hello/test.json',{'project':'demo.json','base_url_name':'alternate','request':{'url':'items','method':'GET'},'expected':{'status':200}})
        response=self.client.post('/api/interoperability/curl',json={'reference':'tag/hello/test.json'})
        self.assertIn('https://alternate.test/api/items',response.json()['curl'])
        self.store.save('projects','demo.json',{**updated,'default_environment':'dev'},expected_revision=saved.revision)
        response=self.client.post('/api/interoperability/curl',json={'reference':'tag/hello/test.json'})
        self.assertIn('https://dev.test/v2/items',response.json()['curl'])

    def test_invalid_source_has_no_persistence(self):
        response=self.client.post('/api/interoperability/preview',json={**self.body,'source':'curl -K private.txt'})
        self.assertEqual(response.status_code,400);self.assertEqual(self.store.list_references('cases'),[])


if __name__=='__main__':unittest.main()
