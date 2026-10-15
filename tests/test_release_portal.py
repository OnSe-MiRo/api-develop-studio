import asyncio
import hashlib
import io
import json
import os
import tempfile
import threading
import time
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from api_test.main import create_app
from api_test.services import studio
from api_test.database import LOCAL_CONTEXT, RequestContext, connect
from api_test.collaboration_store import CollaborationStore
from api_test.release_store import ReleaseStore, ReleaseError
from api_test.services.portal import DOWNLOAD_SLOTS, ArtifactResponse
from test_release_store import spec


def archive(document=None):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as output:
        output.writestr('client/example.py','print("example")\n')
        output.writestr('client/openapi.yaml',json.dumps(document if document is not None else spec()))
    return buffer.getvalue()


def wait_for(client,run,timeout=3):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        response=client.get('/api/runs/'+run)
        if response.status_code!=200:raise AssertionError(response.text)
        result=response.json()
        if result['status'] in ('passed','failed','error','cancelled','timeout'):return result
        time.sleep(.01)
    raise AssertionError('Job did not finish')


class ReleasePortalTest(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.path=self.root/'studio.db'
        self.roots={kind:self.root/kind for kind in ('projects','cases','pipelines')}
        self.documents=CollaborationStore(self.path,self.roots);self.documents.initialize(False)
        self.project={'name':'Original','base_url':'https://user:SECRET@example.test/api?token=SECRET&ok=1','environments':{'dev':{'base_url':'https://dev.example.test','variables':{'secret':{'key':'PRIVATE'}}}},'docs_file':{'document':spec()}}
        self.saved=self.documents.save('projects','p.json',self.project)
        self.releases=ReleaseStore(self.path,context=LOCAL_CONTEXT)
        draft=self.releases.create('p.json',{'version':'1.0.0','projectRevision':1})
        self.release=self.releases.transition('p.json',draft['id'],{'revision':1,'state':'published','reason':'Reviewed'})
        self.enterContext(patch.object(studio,'collaboration_store',return_value=self.documents))
        self.app=create_app(studio)
        self.client=self.enterContext(TestClient(self.app,base_url='http://127.0.0.1:8765'))
        self.base='/api/projects/p.json/portal/'+self.release['id']

    def generated(self,snapshot,module,cancel):
        return {'status':'passed','exitCode':0,'_artifact':archive(snapshot['source']['document']),'_artifact_filename':'client.zip','generation':{'sourceDigest':snapshot['sourceDigest']}}

    def submit(self,language='python'):
        response=self.client.post(self.base+'/sdk',json={'language':language})
        self.assertEqual(response.status_code,202,response.text)
        return response.json()['runId']

    def test_document_and_environment_metadata_stay_on_release_revision(self):
        updated={**self.project,'base_url':'https://changed.test','environments':{},'docs_file':{'document':{**spec(),'info':{'title':'Changed','version':'9'}}}}
        self.documents.save('projects','p.json',updated,expected_revision=1)
        response=self.client.get(self.base);self.assertEqual(response.status_code,200,response.text)
        payload=response.json()
        self.assertEqual(payload['document']['info']['title'],'Release fixture')
        self.assertEqual(payload['environments'][1]['url'],'https://dev.example.test')
        self.assertNotIn('SECRET',response.text);self.assertNotIn('PRIVATE',response.text);self.assertNotIn('changed.test',response.text)
        self.assertEqual(response.headers['cache-control'],'private, no-store')

    def test_sdk_job_persists_zip_and_manifest_after_job_and_store_restart(self):
        with patch('api_test.services.portal.execute_snapshot',side_effect=self.generated) as execute:
            run=self.submit();result=wait_for(self.client,run)
        self.assertEqual(result['status'],'passed',result)
        snapshot=execute.call_args.args[0]
        self.assertEqual(snapshot['sourceDigest'],self.release['sourceDigest']);self.assertEqual(snapshot['projectRevision'],1)
        self.assertNotIn('_artifact',json.dumps(result))
        self.app.state.jobs.close()
        # Durable download is independent from process-local jobs and their TTL.
        downloaded=self.client.get(self.base+'/sdk/python')
        self.assertEqual(downloaded.status_code,200,downloaded.text)
        metadata=ReleaseStore(self.path,context=LOCAL_CONTEXT).portal('p.json',self.release['id'])['artifacts'][0]
        self.assertEqual(hashlib.sha256(downloaded.content).hexdigest(),metadata['sha256'])
        with zipfile.ZipFile(io.BytesIO(downloaded.content)) as file:
            manifest=json.loads(file.read('client/studio-release.json'))
            self.assertEqual(manifest['releaseId'],self.release['id']);self.assertEqual(manifest['sourceDigest'],self.release['sourceDigest'])
        self.assertEqual(self.client.post(self.base+'/sdk',json={'language':'python'}).status_code,409)

    def test_cancelled_and_failed_jobs_never_publish_artifacts(self):
        started=threading.Event()
        def waiting(snapshot,module,cancel):
            started.set();cancel.wait(2);return {'status':'cancelled'}
        with patch('api_test.services.portal.execute_snapshot',side_effect=waiting):
            run=self.submit();self.assertTrue(started.wait(1))
            self.assertEqual(self.client.post('/api/runs/'+run+'/cancel',json={}).status_code,200)
            self.assertEqual(wait_for(self.client,run)['status'],'cancelled')
        self.assertEqual(self.client.get(self.base+'/sdk/python').status_code,404)
        self.assertEqual(self.client.get(self.base).json()['artifacts'],[])

    def test_drafts_and_retired_releases_are_hidden_and_purge_is_audited(self):
        draft=self.releases.create('p.json',{'version':'2.0.0','projectRevision':1})
        self.assertEqual(self.client.get('/api/projects/p.json/portal/'+draft['id']).status_code,404)
        self.assertEqual(len(self.client.get('/api/projects/p.json/portal').json()['items']),1)
        with patch('api_test.services.portal.execute_snapshot',side_effect=self.generated):self.assertEqual(wait_for(self.client,self.submit())['status'],'passed')
        self.assertEqual(self.client.post(self.base+'/sdk/python/purge',json={'reason':'too early'}).status_code,409)
        self.releases.transition('p.json',self.release['id'],{'revision':2,'state':'retired','reason':'retired'})
        self.assertEqual(self.client.get(self.base+'/sdk/python').status_code,404)
        self.assertEqual(self.client.post(self.base+'/sdk/python/purge',json={'reason':'Release retired; backup retained'}).status_code,200)
        with closing(connect(self.path)) as db:
            row=db.execute('SELECT payload_base64,purged_by,purge_reason,sha256 FROM api_release_artifacts').fetchone()
        self.assertIsNone(row['payload_base64']);self.assertEqual(row['purged_by'],'local-user');self.assertTrue(row['sha256'])
        self.assertIn('backup',row['purge_reason'])

    def test_retirement_or_revocation_during_generation_prevents_publication(self):
        started=threading.Event();finish=threading.Event()
        def blocked(snapshot,module,cancel):started.set();finish.wait(2);return self.generated(snapshot,module,cancel)
        with patch('api_test.services.portal.execute_snapshot',side_effect=blocked):
            run=self.submit();self.assertTrue(started.wait(1))
            self.releases.transition('p.json',self.release['id'],{'revision':2,'state':'retired','reason':'Stop publication'})
            finish.set();self.assertEqual(wait_for(self.client,run)['status'],'error')
        with closing(connect(self.path)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM api_release_artifacts').fetchone()[0],0)

    def test_membership_revoked_during_generation_blocks_durable_commit(self):
        started=threading.Event();finish=threading.Event()
        def blocked(snapshot,module,cancel):started.set();finish.wait(2);return self.generated(snapshot,module,cancel)
        try:
            with patch('api_test.services.portal.execute_snapshot',side_effect=blocked):
                run=self.submit();self.assertTrue(started.wait(1))
                with closing(connect(self.path)) as db,db:db.execute("UPDATE memberships SET status='disabled' WHERE workspace_id='default' AND user_id='local-user'")
                finish.set();self.assertEqual(wait_for(self.client,run)['status'],'error')
            with closing(connect(self.path)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM api_release_artifacts').fetchone()[0],0)
        finally:
            finish.set()
            with closing(connect(self.path)) as db,db:db.execute("UPDATE memberships SET status='active' WHERE workspace_id='default' AND user_id='local-user'")

    def test_download_capacity_and_cancelled_response_release_slot(self):
        held=[]
        try:
            for _ in range(4):self.assertTrue(DOWNLOAD_SLOTS.acquire(False));held.append(True)
            self.assertEqual(self.client.get(self.base+'/sdk/python').status_code,429)
        finally:
            for _ in held:DOWNLOAD_SLOTS.release()
        self.assertTrue(DOWNLOAD_SLOTS.acquire(False))
        response=ArtifactResponse(b'zip')
        async def fail(_):raise asyncio.CancelledError()
        async def check():
            with self.assertRaises(asyncio.CancelledError):await response({'type':'http'},None,fail)
        asyncio.run(check())
        for _ in range(4):self.assertTrue(DOWNLOAD_SLOTS.acquire(False))
        for _ in range(4):DOWNLOAD_SLOTS.release()

    def test_workspace_and_viewer_boundaries(self):
        with closing(connect(self.path)) as db,db:
            db.execute("INSERT INTO users(id,display_name,created_at) VALUES ('viewer','Viewer','now')")
            db.execute("INSERT INTO memberships(workspace_id,user_id,role,created_at) VALUES ('default','viewer','viewer','now')")
            db.execute("INSERT INTO workspaces(id,name,created_at) VALUES ('other','Other','now')")
            db.execute("INSERT INTO memberships(workspace_id,user_id,role,created_at) VALUES ('other','local-user','owner','now')")
        viewer=ReleaseStore(self.path,context=RequestContext('default','viewer'))
        self.assertFalse(viewer.portal('p.json',self.release['id'])['permissions']['generateSdk'])
        with self.assertRaises(ReleaseError):viewer.sdk_snapshot('p.json',self.release['id'],'python')
        other_documents=CollaborationStore(self.path,self.roots,context=RequestContext('other','local-user'));other_documents.initialize(False)
        other_documents.save('projects','p.json',self.project)
        other=ReleaseStore(self.path,context=other_documents.context)
        with self.assertRaises(ReleaseError) as error:other.portal('p.json',self.release['id'])
        self.assertEqual(error.exception.status_code,404)
        with self.assertRaises(ReleaseError):other.download_artifact('p.json',self.release['id'],'python')

    def test_portal_migration_backfills_from_old_project_revision(self):
        from api_test.release_store import _schema, canonical, source_hash
        from api_test.migrations import MigrationRunner, Migration
        path=self.root/'legacy.db'
        documents=CollaborationStore(path,{kind:self.root/'legacy'/kind for kind in self.roots});documents.initialize(False)
        original=documents.save('projects','p.json',self.project)
        legacy=ReleaseStore(path,context=LOCAL_CONTEXT)
        source={'kind':'file','document':spec()}
        with closing(connect(path)) as db:
            MigrationRunner((Migration(1,'immutable API releases and approval events',_schema),)).run(db,'release_schema_migrations')
            with db:
                db.execute("INSERT INTO api_releases(id,workspace_id,project_id,project_reference,version,source_revision,source_digest,source_json,document_json,notes,comparison_json,state,revision,created_by,created_at,updated_at,published_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",('legacy-release','default',original.document_id,'p.json','1.0.0',1,source_hash(source),canonical(source),canonical(spec()),'',canonical({'issues':[],'changes':[]}),'published',2,'local-user','2026-10-13','2026-10-13','2026-10-13'))
                legacy._event(db,'legacy-release',1,None,'draft','created',False,'2026-10-13')
                legacy._event(db,'legacy-release',2,'draft','published','approved',False,'2026-10-13')
        documents.save('projects','p.json',{**self.project,'base_url':'https://later.test','environments':{}},expected_revision=1)
        result=legacy.portal('p.json','legacy-release')
        self.assertEqual(result['environments'][1]['url'],'https://dev.example.test')
        self.assertNotIn('later.test',json.dumps(result))
        self.assertNotIn('SECRET',json.dumps(result));self.assertNotIn('PRIVATE',json.dumps(result))

    def test_deleted_project_artifacts_can_be_purged_without_losing_audit_metadata(self):
        with patch('api_test.services.portal.execute_snapshot',side_effect=self.generated):self.assertEqual(wait_for(self.client,self.submit())['status'],'passed')
        self.documents.delete('projects','p.json')
        self.assertEqual(self.client.post(self.base+'/sdk/python/purge',json={'reason':'Deleted project cleanup'}).status_code,200)
        self.documents.save('projects','p.json',self.project,expected_revision=1)
        result=self.client.get(self.base)
        self.assertEqual(result.status_code,200,result.text)
        self.assertTrue(result.json()['artifacts'][0]['purgedAt'])
        self.assertEqual(self.client.get(self.base+'/sdk/python').status_code,404)

    def test_storage_quota_rejects_new_artifact_without_replacing_existing(self):
        data=archive();digest=self.release['sourceDigest']
        self.releases.keep_artifact('p.json',self.release['id'],'python',data,'client.zip',digest,'7.24.0')
        with patch('api_test.release_store.MAX_WORKSPACE_ARTIFACT_BYTES',len(data)):
            with self.assertRaises(ReleaseError) as error:self.releases.keep_artifact('p.json',self.release['id'],'go',data,'go.zip',digest,'7.24.0')
            self.assertEqual(error.exception.status_code,429)
        self.assertEqual(len(self.releases.portal('p.json',self.release['id'])['artifacts']),1)

    def test_commit_boundary_rejects_late_cancellation(self):
        from api_test.jobs import JobManager
        manager=JobManager(workers=1);self.addCleanup(manager.close)
        committed=threading.Event();finish=threading.Event()
        def task(job):
            with manager.condition:job.committed=True;committed.set()
            finish.wait(2)
            return {'status':'passed'}
        run=manager.submit(task)['runId'];self.assertTrue(committed.wait(1))
        manager.cancel(run)
        self.assertFalse(manager.jobs[run].cancel.is_set())
        finish.set();self.assertTrue(manager.jobs[run].done.wait(1))
        self.assertEqual(manager.get(run)['status'],'passed')

    def test_wrong_zip_source_is_not_persisted_even_with_matching_report_hash(self):
        def mismatch(snapshot,module,cancel):
            result=self.generated(snapshot,module,cancel)
            result['_artifact']=archive({**snapshot['source']['document'],'info':{'title':'Wrong','version':'9'}})
            return result
        with patch('api_test.services.portal.execute_snapshot',side_effect=mismatch):
            self.assertEqual(wait_for(self.client,self.submit())['status'],'error')
        self.assertEqual(self.releases.portal('p.json',self.release['id'])['artifacts'],[])

    def test_request_cannot_override_release_source_revision_or_workspace(self):
        with patch('api_test.services.portal.execute_snapshot',side_effect=self.generated) as execute:
            response=self.client.post(self.base+'/sdk',json={'language':'python','projectRevision':999,'workspace_id':'other','source':{'document':'evil'}})
            self.assertEqual(response.status_code,202,response.text)
            self.assertEqual(wait_for(self.client,response.json()['runId'])['status'],'passed')
        snapshot=execute.call_args.args[0]
        self.assertEqual(snapshot['projectRevision'],1)
        self.assertEqual(snapshot['source']['document'],spec())

    def test_wrong_generator_source_digest_is_not_persisted(self):
        def mismatch(snapshot,module,cancel):
            result=self.generated(snapshot,module,cancel);result['generation']['sourceDigest']='b'*64;return result
        with patch('api_test.services.portal.execute_snapshot',side_effect=mismatch):
            self.assertEqual(wait_for(self.client,self.submit())['status'],'error')
        self.assertEqual(self.releases.portal('p.json',self.release['id'])['artifacts'],[])

    def test_corrupt_payload_fails_closed(self):
        with patch('api_test.services.portal.execute_snapshot',side_effect=self.generated):self.assertEqual(wait_for(self.client,self.submit())['status'],'passed')
        with closing(connect(self.path)) as db,db:db.execute("UPDATE api_release_artifacts SET payload_base64='broken'")
        self.assertEqual(self.client.get(self.base+'/sdk/python').status_code,503)

    def test_duplicate_jobs_cannot_replace_retained_sdk(self):
        gate=threading.Barrier(2)
        def generated(snapshot,module,cancel):gate.wait(2);return self.generated(snapshot,module,cancel)
        with patch('api_test.services.portal.execute_snapshot',side_effect=generated):
            first=self.submit();second=self.submit()
            statuses=[wait_for(self.client,run)['status'] for run in (first,second)]
        self.assertCountEqual(statuses,['passed','error'])
        self.assertEqual(len(self.releases.portal('p.json',self.release['id'])['artifacts']),1)

if __name__=='__main__':unittest.main()
