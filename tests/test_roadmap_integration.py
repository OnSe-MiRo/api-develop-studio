"""Cross-feature HTTP contracts under verified workspace identities."""
import io
import json
import threading
import time
import unittest
import zipfile
from contextlib import closing
from unittest.mock import patch

from api_test.database import connect
from api_test.jobs import JobManager
from api_test.oauth_vault import Vault
from api_test.request_scope import bind_context
from api_test.services import studio
import test_workspace_isolation as workspace_fixture


class RoadmapIntegrationTest(unittest.TestCase):
    setUp = workspace_fixture.WorkspaceIsolationTest.setUp
    headers = workspace_fixture.WorkspaceIsolationTest.headers
    get = workspace_fixture.WorkspaceIsolationTest.get

    def post(self, path, body, user='team-a-owner'):
        return self.client.post(path, json=body, headers=self.headers(user))

    def wait(self, run, user='team-a-runner'):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            response=self.get('/api/runs/'+run,user)
            self.assertEqual(response.status_code,200,response.text)
            value=response.json()
            if value['status'] not in ('queued','running'):return value
            time.sleep(.01)
        self.fail('job did not finish')

    def spec_project(self):
        for name,store in self.stores.items():
            current=store.get('projects','same.json')
            store.save('projects','same.json',{**current.document,'docs_file':{'document':{
                'openapi':'3.0.3','info':{'title':name,'version':'1'},'paths':{}}}},expected_revision=current.revision)

    def generated(self,snapshot,*args,**kwargs):
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w') as target:
            target.writestr('client/openapi.yaml',json.dumps(snapshot['source']['document']))
        return {'status':'passed','exitCode':0,'generation':{'sourceDigest':snapshot['sourceDigest']},'_artifact':archive.getvalue(),'_artifact_filename':'client.zip'}

    def test_oauth_issue_and_quick_execution_use_same_workspace_and_user(self):
        profile={'type':'OAuth 2.0','grantType':'client_credentials','clientId':'client','clientSecret':'{{project.token}}','tokenUrl':'https://issuer.example.test/token','clientAuthMethod':'basic','scopes':['read']}
        for name,store in self.stores.items():
            current=store.get('projects','same.json')
            store.save('projects','same.json',{**current.document,'auth_profiles':{'service':profile}},expected_revision=current.revision)
        def issue(*args,**kwargs):
            return {'access_token':kwargs['client_secret']+'-TOKEN','token_type':'Bearer','expires_in':3600}
        with patch('api_test.ownership.OwnershipStore.authorize'), patch('api_test.oauth_service.post_token_form',side_effect=issue) as mint, patch.object(studio,'execute_http_call',return_value=(200,{},'{}',1)) as execute:
            for name in self.stores:
                user=name+'-runner'
                response=self.post('/api/projects/same.json/oauth/profiles/service/token',{'action':'issue'},user)
                self.assertEqual(response.status_code,200,response.text)
                response=self.post('/api/request',{'project':'same.json','url':'/protected','auth_profile':'service'},user)
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(execute.call_args.kwargs['headers']['Authorization'],'Bearer '+name+'-SECRET-TOKEN')
                self.assertNotIn('SECRET',response.text)
            self.assertEqual(mint.call_count,2)
            denied=self.post('/api/projects/same.json/oauth/profiles/service/token',{'action':'issue'},'team-a-viewer')
            self.assertEqual(denied.status_code,403)
        with closing(connect(self.root/'studio.db')) as db:
            rows=db.execute('SELECT workspace_id,user_id FROM oauth_tokens ORDER BY workspace_id').fetchall()
            self.assertEqual([(row[0],row[1]) for row in rows],[('team-a','team-a-runner'),('team-b','team-b-runner')])
            self.assertGreater(db.execute("SELECT COUNT(*) FROM security_events WHERE action='secret.read_requested'").fetchone()[0],0)

    def test_import_applies_only_to_current_workspace_and_respects_roles(self):
        body={'project':'same.json','format':'curl','source':'curl https://example.test/integrated'}
        preview=self.post('/api/interoperability/preview',body,'team-a-viewer')
        self.assertEqual(preview.status_code,200,preview.text)
        item=preview.json()['items'][0]; apply={**body,'index':item['index'],'digest':item['digest']}
        self.assertEqual(self.post('/api/interoperability/apply',apply,'team-a-runner').status_code,403)
        saved=self.post('/api/interoperability/apply',apply,'team-a-editor')
        self.assertEqual(saved.status_code,200,saved.text)
        self.assertIsNotNone(self.stores['team-a'].get('cases',item['reference']))
        self.assertIsNone(self.stores['team-b'].get('cases',item['reference']))
        exported=self.post('/api/interoperability/curl',{'reference':item['reference']},'team-b-viewer')
        self.assertEqual(exported.status_code,404,exported.text)

    def test_sdk_snapshot_artifact_and_jobs_are_workspace_private(self):
        self.spec_project()
        with patch('api_test.services.sdk_generation.execute_snapshot',side_effect=self.generated):
            accepted=self.post('/api/generations',{'project':'same.json','language':'python','projectRevision':2},'team-a-runner')
            self.assertEqual(accepted.status_code,202,accepted.text)
            run=accepted.json()['runId'];result=self.wait(run)
        self.assertEqual(result['status'],'passed',result)
        self.assertEqual(self.get('/api/generations/'+run+'/artifact','team-a-runner').status_code,200)
        self.assertEqual(self.get('/api/generations/'+run+'/artifact','team-b-runner').status_code,404)
        self.assertEqual(self.get('/api/runs/'+run,'team-a-viewer').status_code,404)

    def test_queued_sdk_rechecks_membership_before_generator(self):
        self.spec_project();self.app.state.jobs.close();manager=JobManager(workers=1,capacity=4)
        self.app.state.jobs=manager;self.addCleanup(manager.close)
        gate=threading.Event();started=threading.Event()
        def occupy(job):started.set();gate.wait(3);return {'status':'passed'}
        manager.submit(occupy);self.assertTrue(started.wait(1))
        with patch('api_test.services.sdk_generation.execute_snapshot',side_effect=self.generated) as generate:
            accepted=self.post('/api/generations',{'project':'same.json','language':'python','projectRevision':2},'team-a-runner')
            self.assertEqual(accepted.status_code,202,accepted.text);run=accepted.json()['runId']
            with closing(connect(self.root/'studio.db')) as db,db:db.execute("UPDATE memberships SET role='viewer' WHERE user_id='team-a-runner'")
            gate.set();result=self.wait(run)
            self.assertEqual(result['status'],'error',result);generate.assert_not_called()

    def test_release_portal_sdk_share_revision_but_not_workspace(self):
        self.spec_project();base='/api/projects/same.json/releases'
        created=self.post(base,{'version':'1.0.0','projectRevision':2,'notes':'integration'})
        self.assertEqual(created.status_code,201,created.text);release=created.json();rid=release['id']
        published=self.post(base+'/'+rid+'/transition',{'state':'published','revision':1,'reason':'reviewed','acknowledgeBreaking':True})
        self.assertEqual(published.status_code,200,published.text)
        portal='/api/projects/same.json/portal/'+rid
        self.assertEqual(self.get(portal,'team-a-viewer').status_code,200)
        self.assertEqual(self.get(portal,'team-b-owner').status_code,404)
        with patch('api_test.services.portal.execute_snapshot',side_effect=self.generated):
            accepted=self.post(portal+'/sdk',{'language':'python'},'team-a-runner')
            self.assertEqual(accepted.status_code,202,accepted.text);result=self.wait(accepted.json()['runId'])
        self.assertEqual(result['status'],'passed',result)
        artifact=self.get(portal+'/sdk/python','team-a-viewer')
        self.assertEqual(artifact.status_code,200,artifact.text if artifact.status_code!=200 else '')
        with zipfile.ZipFile(io.BytesIO(artifact.content)) as archive:
            manifest=json.loads(archive.read('client/studio-release.json'))
        self.assertEqual(manifest['sourceDigest'],release['sourceDigest'])
        self.assertEqual(manifest['projectRevision'],2)
        self.assertEqual(self.get(portal+'/sdk/python','team-b-owner').status_code,404)

    def test_shutdown_keeps_committed_release_job_successful(self):
        manager=JobManager(workers=1)
        committed=threading.Event();finish=threading.Event()
        def task(job):
            with manager.condition:
                job.committed=True
                committed.set()
            finish.wait(3)
            return {'status':'passed','result':{'releaseId':'durable-fixture'}}
        run=manager.submit(task)['runId']
        self.assertTrue(committed.wait(1))
        closer=threading.Thread(target=manager.close)
        closer.start()
        try:
            deadline=time.monotonic()+1
            while not manager.closed and time.monotonic()<deadline:time.sleep(.005)
            self.assertTrue(manager.closed)
            self.assertFalse(manager.jobs[run].cancel.is_set())
        finally:
            finish.set();closer.join(4)
        self.assertFalse(closer.is_alive())
        self.assertEqual(manager.get(run)['status'],'passed')
