import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from copy import deepcopy

from api_test.database import LOCAL_CONTEXT, RequestContext, connect
from api_test.collaboration_store import CollaborationStore
from api_test.release_store import ReleaseStore, ReleaseError, source_hash


def spec(deprecated=False):
    return {'openapi':'3.0.3','info':{'title':'Release fixture','version':'1.0.0'},'paths':{'/items':{'get':{'operationId':'listItems','summary':'List','deprecated':deprecated,'responses':{'200':{'description':'ok'}}}}}}


class ReleaseStoreTest(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.path=self.root/'studio.db'
        self.roots={key:self.root/key for key in ('projects','cases','pipelines')}
        self.documents=CollaborationStore(self.path,self.roots);self.documents.initialize(False)
        self.project={'name':'Private project','base_url':'https://private.example.test','variables':{'plain':{'private':'DO-NOT-SNAPSHOT'}},'auth_profiles':{'x':'DO-NOT-SNAPSHOT'},'docs_file':{'name':'openapi.json','document':spec(True)}}
        self.saved=self.documents.save('projects','team/demo.json',self.project)
        self.store=ReleaseStore(self.path,context=LOCAL_CONTEXT)

    def create(self,version='1.0.0',**extra):
        return self.store.create('team/demo.json',{'version':version,'projectRevision':self.saved.revision,'notes':'Release notes',**extra})

    def transition(self,item,state,**extra):
        return self.store.transition('team/demo.json',item['id'],{'revision':item['revision'],'state':state,'reason':'Reviewed release',**extra})

    def update(self,document):
        self.project={**self.project,'docs_file':{'name':'openapi.json','document':document}}
        self.saved=self.documents.save('projects','team/demo.json',self.project,expected_revision=self.saved.revision)

    def test_snapshot_is_immutable_and_contains_only_source(self):
        item=self.create(); original=self.store.source('team/demo.json',item['id'])
        self.assertNotIn('DO-NOT-SNAPSHOT',json.dumps(original));self.assertNotIn('private.example.test',json.dumps(original))
        self.assertEqual(item['sourceDigest'],source_hash(original['source']))
        self.assertEqual(item['deprecatedOperations'],[{'method':'GET','path':'/items','operationId':'listItems'}])
        self.update({**spec(),'info':{'title':'Changed','version':'9'}})
        self.assertEqual(self.store.source('team/demo.json',item['id']),original)
        reopened=ReleaseStore(self.path,context=LOCAL_CONTEXT)
        self.assertEqual(reopened.detail('team/demo.json',item['id'])['projectRevision'],1)

    def test_publish_deprecate_retire_and_server_actor_history(self):
        item=self.create(approvedBy='spoof',state='published')
        self.assertEqual(item['state'],'draft')
        for state in ('published','deprecated','retired'):
            item=self.transition(item,state,approvedBy='spoof',workspace_id='other')
        self.assertEqual([event['to_state'] for event in item['events']],['draft','published','deprecated','retired'])
        self.assertEqual({event['actor_id'] for event in item['events']},{LOCAL_CONTEXT.user_id})
        self.assertEqual(item['revision'],4)
        with self.assertRaises(ReleaseError):self.transition(item,'published')

    def test_duplicate_version_and_stale_project_are_conflicts(self):
        self.create()
        with self.assertRaises(ReleaseError) as conflict:self.create()
        self.assertEqual(conflict.exception.status_code,409)
        self.update(spec())
        with self.assertRaises(ReleaseError):self.store.create('team/demo.json',{'version':'2.0.0','projectRevision':1})

    def test_change_comparison_requires_explicit_acknowledgement(self):
        first=self.transition(self.create(),'published')
        changed=spec();changed['paths']={};self.update(changed)
        second=self.create('2.0.0')
        self.assertEqual(second['baselineId'],first['id'])
        self.assertEqual(second['comparison']['operationChanges'],[{'kind':'removed','path':'/items','method':'GET'}])
        self.assertIn('operation_removed',{x['code'] for x in second['comparison']['changes']})
        with self.assertRaises(ReleaseError):self.transition(second,'published')
        published=self.transition(second,'published',acknowledgeChanges=True)
        self.assertEqual(published['events'][-1]['acknowledge_changes'],1)
        self.assertEqual(published['sourceDigest'],second['sourceDigest'])

    def test_concurrent_transition_has_one_winner_and_no_extra_event(self):
        draft=self.create()
        def publish(_):
            try:return self.transition(draft,'published')['state']
            except ReleaseError as error:return error.status_code
        with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(publish,range(2)))
        self.assertCountEqual(results,['published',409])
        self.assertEqual(len(self.store.detail('team/demo.json',draft['id'])['events']),2)

    def test_event_failure_rolls_back_transition_and_creation(self):
        draft=self.create()
        with patch.object(self.store,'_event',side_effect=RuntimeError('fixture failure')):
            with self.assertRaises(RuntimeError):self.transition(draft,'published')
            with self.assertRaises(RuntimeError):self.create('2.0.0')
        self.assertEqual(self.store.detail('team/demo.json',draft['id'])['revision'],1)
        self.assertEqual(len(self.store.list('team/demo.json')['items']),1)
        self.assertEqual(self.create('2.0.0')['state'],'draft')

    def seed_context(self,workspace,user,role):
        with closing(connect(self.path)) as db,db:
            db.execute('INSERT OR IGNORE INTO workspaces(id,name,created_at) VALUES (?,?,?)',(workspace,workspace,'now'))
            db.execute('INSERT OR IGNORE INTO users(id,display_name,created_at) VALUES (?,?,?)',(user,user,'now'))
            db.execute('INSERT INTO memberships(workspace_id,user_id,role,created_at) VALUES (?,?,?,?)',(workspace,user,role,'now'))
        return RequestContext(workspace,user,'request-fixture')

    def test_roles_and_cross_workspace_reference_and_cursor(self):
        draft=self.create()
        for role in ('owner','admin','editor','runner','viewer'):
            store=ReleaseStore(self.path,context=self.seed_context('default','user-'+role,role))
            self.assertEqual(store.detail('team/demo.json',draft['id'])['id'],draft['id'])
            if role in ('runner','viewer'):
                with self.assertRaises(ReleaseError):store.create('team/demo.json',{'version':'3.0.0','projectRevision':1})
            if role not in ('owner','admin'):
                with self.assertRaises(ReleaseError):store.transition('team/demo.json',draft['id'],{'state':'published','revision':1,'reason':'no'})
        context=self.seed_context('other','other','owner')
        documents=CollaborationStore(self.path,self.roots,context=context);documents.initialize(False)
        documents.save('projects','team/demo.json',self.project)
        other=ReleaseStore(self.path,context=context)
        self.assertEqual(other.list('team/demo.json')['items'],[])
        for action in (lambda:other.detail('team/demo.json',draft['id']),lambda:other.source('team/demo.json',draft['id']),lambda:other.list('team/demo.json',before=draft['id']),lambda:other.create('team/demo.json',{'version':'1.0.0','projectRevision':1,'baselineId':draft['id']})):
            with self.assertRaises(ReleaseError) as error:action()
            self.assertEqual(error.exception.status_code,404)

    def test_pagination_is_stable_and_does_not_include_source(self):
        expected=[self.create(f'1.0.{i}')['id'] for i in range(5)][::-1]
        first=self.store.list('team/demo.json',limit=2)
        second=self.store.list('team/demo.json',limit=2,before=first['nextCursor'])
        third=self.store.list('team/demo.json',limit=2,before=second['nextCursor'])
        self.assertEqual([x['id'] for x in first['items']+second['items']+third['items']],expected)
        self.assertIsNone(third['nextCursor'])
        self.assertNotIn('source_json',first['items'][0]);self.assertNotIn('comparison',first['items'][0])

    def test_url_only_invalid_refs_and_bad_transitions_are_rejected(self):
        for document in [None,{**spec(),'components':{'schemas':{'Bad':{'$ref':'file:///etc/passwd'}}}}]:
            current=self.documents.get('projects','team/demo.json')
            project={'name':'URL','base_url':'https://example.test','docs_url':'https://example.test/openapi.json'} if document is None else {**self.project,'docs_file':{'document':document}}
            saved=self.documents.save('projects','team/demo.json',project,expected_revision=current.revision)
            with self.assertRaises(ReleaseError):self.store.create('team/demo.json',{'version':'1.0.0','projectRevision':saved.revision})
        self.assertEqual(self.store.list('team/demo.json')['items'],[])

    def test_bundle_preserves_raw_file_text_and_project_deletion_hides_release(self):
        files={'openapi.yaml':'openapi: 3.0.3\ninfo: {title: Test, version: "1"}\npaths: {}\n'}
        saved=self.documents.save('projects','bundle.json',{'docs_bundle':{'entrypoint':'openapi.yaml','files':files}})
        draft=self.store.create('bundle.json',{'version':'1.0.0','projectRevision':saved.revision})
        self.assertEqual(self.store.source('bundle.json',draft['id'])['source']['files'],files)
        self.documents.delete('projects','bundle.json')
        with self.assertRaises(ReleaseError) as error:self.store.detail('bundle.json',draft['id'])
        self.assertEqual(error.exception.status_code,404)

if __name__=='__main__':unittest.main()
