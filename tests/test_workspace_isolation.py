"""Trusted identity adapter fixtures exercise the real HTTP/storage boundaries."""
import json
import os
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from contextlib import closing

from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from api_test.main import create_app
from api_test.services import studio
from api_test.database import RequestContext, LOCAL_CONTEXT, connect
from api_test.collaboration_store import CollaborationStore
from api_test.request_scope import CurrentUser, bind_context, current_context
from api_test.execution_history import ExecutionHistory
from api_test.jobs import JobManager
from api_test.services.mock import MockServerManager


class WorkspaceIsolationTest(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.roots={kind:self.root/kind for kind in ('projects','cases','pipelines')}
        for path in self.roots.values():path.mkdir()
        for key,value in {'ROOT':self.root,'PROJECT_ROOT':self.roots['projects'],'CASE_ROOT':self.roots['cases'],'PIPELINE_ROOT':self.roots['pipelines'],'_COLLABORATION_STORE':None}.items():
            self.enterContext(patch.object(studio,key,value))
        self.enterContext(patch.dict(os.environ,{'STUDIO_DB_PATH':str(self.root/'studio.db'),'STUDIO_DATABASE_URL':'','STUDIO_DATABASE_URL_FILE':'','LOCAL_SERVER':'false','STUDIO_AUTH_MODE':'remote','EXAMPLE_PROJECT':'false','API_TEST_ENCRYPTION_KEY':Fernet.generate_key().decode(),'API_TEST_ENCRYPTION_URL':'','STUDIO_OWNERSHIP_DB_PATH':str(self.root/'ownership.db')}))
        studio.collaboration_store()
        self.contexts={}
        with closing(connect(self.root/'studio.db')) as db,db:
            for workspace in ('team-a','team-b'):
                db.execute("INSERT INTO workspaces(id,name,created_at,status) VALUES (?,?,?,'active')",(workspace,workspace,'2026-10-13'))
                for role in ('owner','admin','editor','runner','viewer'):
                    user=workspace+'-'+role
                    db.execute("INSERT INTO users(id,display_name,created_at,status) VALUES (?,?,?,'active')",(user,user,'2026-10-13'))
                    db.execute("INSERT INTO memberships(workspace_id,user_id,role,created_at,status) VALUES (?,?,?,?,'active')",(workspace,user,role,'2026-10-13'))
                    self.contexts[user]=RequestContext(workspace,user)
        self.stores={}
        for workspace in ('team-a','team-b'):
            context=self.contexts[workspace+'-owner']
            store=CollaborationStore(self.root/'studio.db',self.roots,context=context);store.initialize(import_existing=False)
            store.save('projects','same.json',{'name':workspace,'base_url':'https://example.test','variables':{'plain':{'label':workspace},'secret':{'token':studio.encrypt_secret(workspace+'-SECRET') if hasattr(studio,'encrypt_secret') else Fernet(os.environ['API_TEST_ENCRYPTION_KEY'].encode()).encrypt((workspace+'-SECRET').encode()).decode()}}},actor_id=context.user_id)
            store.save('cases','tag/api/same.json',{'project':'same.json','request':{'url':'/echo','method':'GET'},'expected':{'status':200}},actor_id=context.user_id)
            self.stores[workspace]=store
        self.app=create_app(studio)
        # Synthetic authentication adapter is installed only in this fixture. Production
        # has no header identity adapter; provider must validate credentials itself.
        self.app.state.current_user_provider=lambda request: CurrentUser(self.contexts[request.headers['test-principal']].user_id,self.contexts[request.headers['test-principal']].workspace_id) if request.headers.get('test-principal') in self.contexts else None
        self.client=self.enterContext(TestClient(self.app))
        self.addCleanup(self.app.state.jobs.close)

    def headers(self,principal='team-a-owner',**extra):return {'test-principal':principal,**extra}
    def get(self,path,principal='team-a-owner',**extra):return self.client.get(path,headers=self.headers(principal,**extra))

    def test_same_reference_documents_revision_and_secret_do_not_cross(self):
        for workspace in ('team-a','team-b'):
            user=workspace+'-viewer';response=self.get('/api/projects/same.json',user)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['name'],workspace)
            self.assertNotIn('SECRET',response.text)
            revisions=self.get('/api/projects/same.json/revisions',user)
            self.assertEqual(revisions.status_code,200)
            self.assertEqual(revisions.json()['items'][0]['created_by'],workspace+'-owner')
        denied=self.get('/api/projects/same.json','team-a-owner',**{'X-Studio-Workspace':'team-b','X-Studio-Actor':'team-b-owner'})
        self.assertEqual(denied.status_code,403)
        for url in ('/api/projects/_workspaces/team-b/same.json','/api/projects/_workspaces%2Fteam-b%2Fsame.json'):
            self.assertNotEqual(self.get(url).status_code,200)

    def test_actor_and_body_workspace_cannot_override_audit_identity(self):
        response=self.client.put('/api/projects/new.json',headers=self.headers('team-a-editor',**{'X-Studio-Actor':'team-b-owner'}),json={'name':'New','base_url':'https://example.test','workspace_id':'team-b','user_id':'team-b-owner'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIsNone(self.stores['team-b'].get('projects','new.json'))
        stored=self.stores['team-a'].get('projects','new.json')
        self.assertNotIn('workspace_id',stored.document)
        with closing(connect(self.root/'studio.db')) as db:
            row=db.execute('SELECT workspace_id,actor_id,request_id FROM audit_events WHERE document_id=?',(stored.document_id,)).fetchone()
        self.assertEqual(row['workspace_id'],'team-a');self.assertEqual(row['actor_id'],'team-a-editor');self.assertTrue(row['request_id'])

    def test_role_read_and_edit_matrix(self):
        for role in ('owner','admin','editor','runner','viewer'):
            with self.subTest(role=role):
                user='team-a-'+role
                self.assertEqual(self.get('/api/projects',user).status_code,200)
                response=self.client.put('/api/projects/'+role+'.json',headers=self.headers(user),json={'name':role,'base_url':'https://example.test'})
                self.assertEqual(response.status_code,200 if role in ('owner','admin','editor') else 403,response.text)

    def test_run_and_admin_role_matrix_blocks_before_dispatch(self):
        with patch.object(studio,'handle_api_request',return_value={'status':200}) as execute, patch.object(studio.StudioRequest,'ownership_action',lambda request,parts:request.json_response(200,{'ok':True})):
            for role in ('owner','admin','editor','runner','viewer'):
                user='team-a-'+role
                response=self.client.post('/api/request',headers=self.headers(user),json={'url':'https://example.test'})
                self.assertEqual(response.status_code,403 if role=='viewer' else 200,response.text)
                response=self.client.post('/api/ownership/grant',headers=self.headers(user),json={})
                self.assertEqual(response.status_code,200 if role in ('owner','admin') else 403,response.text)
            self.assertEqual(execute.call_count,4)

    def test_user_and_workspace_status_are_rechecked(self):
        for table,column,value in [('users','id','team-a-viewer'),('workspaces','id','team-a')]:
            with self.subTest(table=table):
                self.assertEqual(self.get('/api/projects','team-a-viewer').status_code,200)
                with closing(connect(self.root/'studio.db')) as db,db:db.execute(f"UPDATE {table} SET status='disabled' WHERE {column}=?",(value,))
                self.assertEqual(self.get('/api/projects','team-a-viewer').status_code,403)
                self.assertEqual(self.get('/api/projects','team-b-viewer').status_code,200)
                with closing(connect(self.root/'studio.db')) as db,db:db.execute(f"UPDATE {table} SET status='active' WHERE {column}=?",(value,))

    def test_real_mock_lifecycle_does_not_stop_other_workspace(self):
        for workspace,store in self.stores.items():
            saved=store.get('projects','same.json')
            document={**saved.document,'docs_file':{'name':'openapi.json','document':{'openapi':'3.0.3','info':{'title':workspace,'version':'1'},'paths':{'/hello':{'get':{'responses':{'200':{'description':'ok'}}}}}}}}
            store.save('projects','same.json',document,expected_revision=saved.revision)
        responses=[]
        for workspace,seed in [('team-a',11),('team-b',22)]:
            response=self.client.post('/api/projects/same.json/mock/start',headers=self.headers(workspace+'-runner'),json={'seed':seed})
            self.assertEqual(response.status_code,200,response.text);responses.append(response.json())
        self.assertNotEqual(responses[0]['port'],responses[1]['port'])
        self.assertEqual(self.client.post('/api/projects/same.json/mock/stop',headers=self.headers('team-a-runner'),json={}).status_code,200)
        self.assertEqual(self.get('/api/projects/same.json/mock','team-a-viewer').json()['status'],'stopped')
        other=self.get('/api/projects/same.json/mock','team-b-viewer').json()
        self.assertEqual(other['status'],'running');self.assertEqual(other['seed'],22)
        self.assertEqual(self.client.post('/api/projects/same.json/mock/stop',headers=self.headers('team-b-viewer'),json={}).status_code,403)

    def test_concurrent_request_context_and_quick_secret_resolution(self):
        observed=[];lock=threading.Lock()
        def fake_call(url,**kwargs):
            with lock:observed.append((current_context().workspace_id,kwargs.get('headers',{})))
            time.sleep(.01)
            return 200,{},'{"ok":true}',1
        with patch.object(studio,'execute_http_call',side_effect=fake_call),patch('api_test.ownership.OwnershipStore.authorize'):
            def run(workspace):
                response=self.client.post('/api/request',headers=self.headers(workspace+'-runner'),json={'project':'same.json','url':'/echo','headers':{'X-Token':'{{project.token}}'}})
                self.assertEqual(response.status_code,200,response.text)
                self.assertNotIn('SECRET',response.text)
            with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(run,['team-a','team-b']*6))
        for workspace,headers in observed:self.assertEqual(headers['X-Token'],workspace+'-SECRET')
        self.assertEqual(current_context(),LOCAL_CONTEXT)

    def test_job_context_owner_and_history_are_scoped(self):
        captured=[]
        def execute(job,command,module,*args):
            captured.append((current_context(),command))
            return {'status':'passed','exitCode':0}
        with patch('api_test.services.execution.execute_job',side_effect=execute):
            response=self.client.post('/api/runs',headers=self.headers('team-a-runner'),json={'cases':['tag/api/same.json'],'workspace_id':'team-b'})
            self.assertEqual(response.status_code,202,response.text);run=response.json()['runId']
            end=time.monotonic()+2
            while time.monotonic()<end and self.get('/api/runs/'+run,'team-a-runner').json()['status'] not in ('passed','error'):time.sleep(.01)
        self.assertEqual(self.get('/api/runs/'+run,'team-a-runner').json()['status'],'passed')
        self.assertEqual(self.get('/api/runs/'+run,'team-b-runner').status_code,404)
        self.assertEqual(self.client.post('/api/runs/'+run+'/cancel',headers=self.headers('team-b-runner'),json={}).status_code,404)
        self.assertEqual(captured[0][0].workspace_id,'team-a')
        command=' '.join(captured[0][1]);self.assertIn('_workspaces/team-a',command);self.assertNotIn('team-b',command)
        context=self.contexts['team-a-runner']
        history=ExecutionHistory(self.root/'studio.db',context=context)
        history.record(run_id='history-a',started_at='2026-10-13T00:00:00+00:00',finished_at='2026-10-13T00:00:01+00:00',duration_ms=1,status='passed',exit_code=0,projects=['same.json'],targets=[])
        self.assertEqual(self.get('/api/executions/history-a','team-a-viewer').status_code,200)
        self.assertEqual(self.get('/api/executions/history-a','team-b-owner').status_code,404)

    def test_queued_job_rechecks_revoked_membership(self):
        old=self.app.state.jobs;old.close();self.app.state.jobs=JobManager(workers=1)
        manager=self.app.state.jobs;self.addCleanup(manager.close)
        gate=threading.Event();started=threading.Event()
        manager.submit(lambda job:(started.set(),gate.wait(3),{'status':'passed'})[-1]);self.assertTrue(started.wait(1))
        with patch('api_test.services.execution.execute_job') as execute:
            response=self.client.post('/api/runs',headers=self.headers('team-a-runner'),json={'cases':['tag/api/same.json']})
            self.assertEqual(response.status_code,202,response.text)
            with closing(connect(self.root/'studio.db')) as db,db:db.execute("UPDATE memberships SET status='disabled' WHERE user_id='team-a-runner'")
            gate.set();job=manager.jobs[response.json()['runId']];self.assertTrue(job.done.wait(2));self.assertEqual(job.data['status'],'error');execute.assert_not_called()
        self.assertEqual(self.get('/api/projects','team-a-runner').status_code,403)

    def test_uploads_and_mock_registry_use_workspace_keys(self):
        reference='tag/api/files/value.txt'
        for workspace in ('team-a','team-b'):
            response=self.client.post('/api/uploads/'+reference,headers={**self.headers(workspace+'-editor'),'Content-Type':'application/octet-stream'},content=workspace.encode())
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual((self.roots['cases']/'_workspaces'/workspace/reference).read_text(),workspace)
        response=self.client.post('/api/uploads/_workspaces/team-b/files/value.txt',headers=self.headers('team-a-editor'),content=b'evil')
        self.assertEqual(response.status_code,400)
        manager=MockServerManager()
        with bind_context(self.contexts['team-a-owner']):a=manager.scope_key('same.json')
        with bind_context(self.contexts['team-b-owner']):b=manager.scope_key('same.json')
        self.assertNotEqual(a,b)

    def test_reserved_workspace_paths_cannot_be_reached_via_symlink(self):
        from api_test.runner import resolve_case_path, resolve_attachment_path, CaseConfigurationError
        target=self.roots['cases']/'_workspaces'/'team-b'/'tag/api/same.json'
        alias=self.roots['cases']/'alias.json';alias.symlink_to(target)
        with self.assertRaises(studio.ApiError):studio.safe_file(self.roots['cases'],'alias.json')
        with self.assertRaises(CaseConfigurationError):resolve_case_path(self.roots['cases'],'alias.json')
        with self.assertRaises(CaseConfigurationError):resolve_attachment_path(self.roots['cases'],'alias.json')
        studio.collaboration_store().import_existing_files()
        self.assertIsNone(studio.collaboration_store().get('cases','alias.json'))

    def test_load_result_queries_are_scoped(self):
        from api_test.load_results import import_k6_result
        fixtures=Path(__file__).parent/'fixtures'/'load-tests'
        bundle=import_k6_result(fixtures/'smoke-summary.json',fixtures/'smoke-raw.jsonl')
        response=self.client.post('/api/load-tests/runs',headers=self.headers('team-a-editor'),json=bundle)
        self.assertEqual(response.status_code,201,response.text);run=response.json()['id']
        self.assertEqual(self.get('/api/load-tests/runs/'+run,'team-a-viewer').status_code,200)
        for path in ('/api/load-tests/runs/'+run,'/api/load-tests/runs/'+run+'/series','/api/load-tests/compare?baseline='+run+'&candidate='+run):
            self.assertEqual(self.get(path,'team-b-owner').status_code,404)
        self.assertEqual(self.get('/api/load-tests/runs','team-b-viewer').json()['items'],[])
        self.assertEqual(self.client.post('/api/load-tests/runs',headers=self.headers('team-a-runner'),json=bundle).status_code,403)

    def test_actual_subprocess_uses_workspace_files_secrets_and_history(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        observed=[]
        class Echo(BaseHTTPRequestHandler):
            def do_GET(self):
                observed.append(self.headers.get('X-Token'))
                self.send_response(200);self.end_headers();self.wfile.write(b'{"ok":true}')
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Echo)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        for workspace,store in self.stores.items():
            project=store.get('projects','same.json')
            store.save('projects','same.json',{**project.document,'base_url':f'http://127.0.0.1:{server.server_port}'},expected_revision=project.revision)
            case=store.get('cases','tag/api/same.json')
            document={**case.document,'request':{'url':'/echo','headers':{'X-Token':'{{project.token}}'}}}
            store.save('cases','tag/api/same.json',document,expected_revision=case.revision)
        repository=Path(__file__).resolve().parents[1]
        with patch.object(studio,'ROOT',repository),patch.dict(os.environ,{'LOCAL_SERVER':'true','SKIP_OWNERSHIP_VERIFICATION':'true'}):
            for workspace in ('team-a','team-b'):
                user=workspace+'-runner'
                response=self.client.post('http://127.0.0.1/api/runs',headers=self.headers(user),json={'cases':['tag/api/same.json']})
                self.assertEqual(response.status_code,202,response.text);run=response.json()['runId']
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    result=self.client.get('http://127.0.0.1/api/runs/'+run,headers=self.headers(user)).json()
                    if result['status'] in ('passed','failed','error'):break
                    time.sleep(.025)
                self.assertEqual(result['status'],'passed',result)
                self.assertNotIn('SECRET',json.dumps(result))
                history=ExecutionHistory(self.root/'studio.db',context=self.contexts[user]).detail(run)
                self.assertEqual(history['actor'],user)
                other='team-b' if workspace=='team-a' else 'team-a'
                self.assertIsNone(ExecutionHistory(self.root/'studio.db',context=self.contexts[other+'-owner']).detail(run))
        self.assertEqual(observed,['team-a-SECRET','team-b-SECRET'])

    def test_remote_no_provider_and_unrecognized_user_fail_closed(self):
        self.assertEqual(self.client.get('/api/projects').status_code,401)
        self.assertEqual(self.client.get('/health').json(),{'status':'ok'})
        del self.app.state.current_user_provider
        self.assertEqual(self.client.get('/api/projects').status_code,401)
        with patch.dict(os.environ,{'STUDIO_AUTH_MODE':'local'}):
            self.assertEqual(self.client.get('/api/projects').status_code,403) # non-loopback testserver host
            response=self.client.get('http://127.0.0.1/api/projects',headers={'X-Studio-Workspace':'team-b'})
            self.assertEqual(response.status_code,403)
            self.assertEqual(self.client.get('http://127.0.0.1/api/projects').status_code,200)


if __name__=='__main__':unittest.main()
