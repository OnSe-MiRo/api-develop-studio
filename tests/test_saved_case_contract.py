from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json, os, subprocess, sys, tempfile, unittest
from api_test.runner import ApiTestRunner, CaseConfigurationError, project_request_settings
from api_test.reports import RunReport, now, execution_detail
from api_test.contracts.documents import digest
from api_test.services import studio


def contract():
    from test_contract_servers import spec
    doc=spec();doc.pop('servers')
    doc['paths']['/items']['get']['responses']['200']['content']['application/json']['schema']={'type':'object','required':['id'],'properties':{'id':{'type':'integer'}}}
    return doc


def case(enabled=True):
    value={'project':'demo.json','request':{'method':'GET','url':'http://127.0.0.1:12345/items'},'expected':{'status':200}}
    if enabled is not None:value['contract_validation']={'enabled':enabled}
    return value


class SavedCaseContractTests(unittest.TestCase):
    def test_opt_in_adds_to_assertions_and_report_without_values(self):
        with patch('api_test.runner.execute_http_call',return_value=(200,{'Content-Type':'application/json'},'{"id":"PRIVATE"}',1)):
            for enabled in [None,False,True]:
                result=ApiTestRunner().run_case('case',case(enabled),contract_document=contract())
                self.assertEqual(result.status,'failed' if enabled else 'passed')
            self.assertEqual(result.contract['issueCount'],1)
            self.assertNotIn('PRIVATE',str(result.differences))
            report=RunReport();report.add(result,'tag/api/case.json',now(),project='demo.json',case_reference='tag/api/case.json');report.finish(1)
            self.assertEqual(report.data['targets'][0]['errorCategory'],'contract_failed')
            self.assertNotIn('PRIVATE',json.dumps(report.data))
            detail=execution_detail([{'kind':'case','reference':'tag/api/case.json'}],report.data,None,None)
            self.assertEqual(detail['outcomes'][0]['contract'],result.contract)
            self.assertNotIn('PRIVATE',json.dumps(detail))
            with tempfile.TemporaryDirectory() as d:
                report.write(Path(d)/'out.json',Path(d)/'out.xml');self.assertNotIn('PRIVATE',(Path(d)/'out.xml').read_text())
        with patch('api_test.runner.execute_http_call',return_value=(200,{'Content-Type':'application/json'},'{"id":1}',1)):
            value=case();value['expected']['status']=201
            result=ApiTestRunner().run_case('case',value,contract_document=contract())
            self.assertTrue(result.contract['valid']);self.assertEqual(result.status,'failed')

    def test_invalid_config_and_spec_never_send_http(self):
        values=[None,True,{}, {'enabled':'yes'}, {'enabled':True,'server_variables':{'v':3}}, {'enabled':True,'document_url':'file:///PRIVATE'}, {'enabled':True,'unknown':'PRIVATE'}]
        with patch('api_test.runner.execute_http_call') as send:
            for config in values:
                value=case();value['contract_validation']=config
                with self.assertRaises(CaseConfigurationError):ApiTestRunner().run_case('x',value,contract_document=contract())
                with self.assertRaises(studio.ApiError):studio.normalize_case_document(value)
            for doc in [None,{}, {'openapi':'3.0.3','paths':{}}]:
                with self.assertRaises(CaseConfigurationError):ApiTestRunner().run_case('x',case(),contract_document=doc)
            bad=case();bad['request']['url']='http://127.0.0.1:12345/no-operation'
            with self.assertRaises(CaseConfigurationError):ApiTestRunner().run_case('x',bad,contract_document=contract())
        send.assert_not_called()

    def test_retry_freezes_contract_and_supports_server_options(self):
        doc=contract();original=digest(doc)
        def respond(*args,**kwargs):
            doc['paths']['/items']['get']['responses']['200']['content']['application/json']['schema']={}
            return 200,{'Content-Type':'application/json'},'{"id":"PRIVATE"}',1
        with patch('api_test.runner.execute_http_call',side_effect=respond) as send:
            result=ApiTestRunner().run_case('x',case(),retry=1,contract_document=doc)
        self.assertEqual(send.call_count,2);self.assertEqual(result.status,'failed');self.assertEqual(result.contract['documentDigest'],original)
        doc=contract();doc['paths']['/items']['get']['servers']=[{'url':'../{version}','variables':{'version':{'default':'v1'}}}]
        value=case();value['request']['url']='http://127.0.0.1:12345/service/v2/items';value['contract_validation'].update(server_variables={'version':'v2'},document_url='https://docs.test/service/spec/openapi.json')
        with patch('api_test.runner.execute_http_call',return_value=(200,{'Content-Type':'application/json'},'{"id":1}',1)):
            self.assertEqual(ApiTestRunner().run_case('x',value,contract_document=doc).status,'passed')

    def test_project_root_bounds_snapshot_and_url_only_project_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a=root/'a';b=root/'b';a.mkdir();b.mkdir()
            for directory,title in [(a,'A'),(b,'B')]:
                doc=contract();doc['info']['title']=title
                (directory/'demo.json').write_text(json.dumps({'base_url':'http://127.0.0.1:12345','docs_file':{'document':doc}}))
            self.assertEqual(project_request_settings(case(),a).contract_document['info']['title'],'A')
            self.assertEqual(project_request_settings(case(),b).contract_document['info']['title'],'B')
            bad=case();bad['project']='../b/demo.json'
            with self.assertRaises(CaseConfigurationError):project_request_settings(bad,a)
            (a/'demo.json').write_text(json.dumps({'base_url':'http://127.0.0.1:12345','docs_url':'https://test/PRIVATE'}))
            with self.assertRaises(CaseConfigurationError) as error:project_request_settings(case(),a)
            self.assertNotIn('PRIVATE',str(error.exception))
            self.assertIsNone(project_request_settings(case(False),a).contract_document)
            for malformed in [None, 'PRIVATE', []]:
                (a/'demo.json').write_text(json.dumps({'base_url':'http://127.0.0.1:12345','docs_file':malformed}))
                with self.assertRaises(CaseConfigurationError) as error:project_request_settings(case(),a)
                self.assertNotIn('PRIVATE',str(error.exception))


    def test_real_cli_and_pipeline_use_contract_and_sanitized_reports(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from threading import Thread
        seen=[]
        class Target(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                seen.append(self.path);body=b'{"id":"PRIVATE"}'
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Target);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(thread.join,2);self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'projects').mkdir();(root/'case/tag/api').mkdir(parents=True)
            (root/'projects/demo.json').write_text(json.dumps({'base_url':f'http://127.0.0.1:{server.server_port}','docs_file':{'document':contract()}}))
            value=case();value['request']['url']='/items';(root/'case/tag/api/case.json').write_text(json.dumps(value))
            (root/'pipeline.json').write_text(json.dumps({'project':'demo.json','steps':[{'name':'contract-step','case':'tag/api/case.json'}]}))
            env={**os.environ,'LOCAL_SERVER':'true','SKIP_OWNERSHIP_VERIFICATION':'true','STUDIO_AUTH_MODE':'local','API_TEST_HOST':'127.0.0.1','STUDIO_DATABASE_URL':'','STUDIO_DATABASE_URL_FILE':'','STUDIO_DB_PATH':str(root/'db')}
            for target in [['--case','tag/api/case.json'],[str(root/'pipeline.json')]]:
                completed=subprocess.run([sys.executable,'run_api_tests.py',*target,'--case-root',str(root/'case'),'--project-root',str(root/'projects'),'--log-dir',str(root/'logs'),'--report-json',str(root/'report.json'),'--report-junit',str(root/'report.xml')],env=env,capture_output=True,text=True,timeout=30)
                self.assertEqual(completed.returncode,1,completed.stdout+completed.stderr)
                report=json.loads((root/'report.json').read_text());self.assertEqual(report['targets'][0]['errorCategory'],'contract_failed');self.assertFalse(report['targets'][0]['contract']['valid'])
                self.assertNotIn('PRIVATE',(root/'report.json').read_text()+(root/'report.xml').read_text())
        self.assertEqual(seen,['/items','/items'])

class SavedContractWorkspaceTests(unittest.TestCase):
    def setUp(self):
        import test_workspace_isolation
        test_workspace_isolation.WorkspaceIsolationTest.setUp(self)

    def test_http_settings_roundtrip_and_same_name_project_contract_isolation(self):
        for workspace,kind in [('team-a','integer'),('team-b','string')]:
            store=self.stores[workspace];current=store.get('projects','same.json');project=deepcopy(current.document)
            doc=contract();doc['paths']['/items']['get']['responses']['200']['content']['application/json']['schema']['properties']['id']['type']=kind
            project['docs_file']={'document':doc};store.save('projects','same.json',project,expected_revision=current.revision)
        payload=case();payload['project']='same.json'
        response=self.client.put('/api/cases/tag/api/contract.json',headers={'test-principal':'team-a-editor'},json=payload)
        self.assertEqual(response.status_code,200,response.text)
        own=self.client.get('/api/cases/tag/api/contract.json',headers={'test-principal':'team-a-viewer'})
        self.assertTrue(own.json()['contract_validation']['enabled'])
        other=self.client.get('/api/cases/tag/api/contract.json',headers={'test-principal':'team-b-viewer'})
        self.assertNotEqual(other.status_code,200)
        invalid=deepcopy(payload);invalid['contract_validation']={'enabled':'true'}
        self.assertEqual(self.client.put('/api/cases/tag/api/invalid.json',headers={'test-principal':'team-a-editor'},json=invalid).status_code,400)
        with patch('api_test.runner.execute_http_call',return_value=(200,{'Content-Type':'application/json'},'{"id":1}',1)):
            for workspace,expected in [('team-a','passed'),('team-b','failed')]:
                settings=project_request_settings(payload,self.stores[workspace].roots['projects'])
                result=ApiTestRunner().run_case('case',payload,contract_document=settings.contract_document)
                self.assertEqual(result.status,expected)
