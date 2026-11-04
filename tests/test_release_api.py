import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from api_test.collaboration_store import CollaborationStore
from api_test.main import app
from api_test.services import studio
from test_release_store import spec


class ReleaseHTTPTest(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.enterContext(patch.dict(os.environ, {'STUDIO_DB_PATH':str(self.root/'studio.db'),'STUDIO_DATABASE_URL':'','STUDIO_DATABASE_URL_FILE':'','STUDIO_AUTH_MODE':'local'}))
        self.store=CollaborationStore(self.root/'studio.db',{kind:self.root/kind for kind in ('projects','cases','pipelines')})
        self.store.initialize(False)
        self.store.save('projects','folder/demo.json',{'name':'demo','docs_file':{'document':spec()}})
        self.enterContext(patch.object(studio,'collaboration_store',return_value=self.store))
        self.client=self.enterContext(TestClient(app,base_url="http://127.0.0.1:8765"))
        self.base='/api/projects/folder%2Fdemo.json/releases'

    def test_create_read_source_and_transition_contract(self):
        created=self.client.post(self.base,json={'version':'1.0.0','projectRevision':1,'notes':'<script>not executable</script>','approvedBy':'forged'})
        self.assertEqual(created.status_code,201,created.text)
        body=created.json();self.assertEqual(body['state'],'draft')
        self.assertNotIn('forged',created.text)
        self.assertEqual(self.client.get(self.base).json()['items'][0]['id'],body['id'])
        source=self.client.get(self.base+'/'+body['id']+'/source')
        self.assertEqual(source.status_code,200,source.text);self.assertEqual(source.json()['source']['document'],spec())
        published=self.client.post(self.base+'/'+body['id']+'/transition',json={'state':'published','revision':1,'reason':'Verified'})
        self.assertEqual(published.status_code,200,published.text)
        self.assertEqual(self.client.get(self.base+'/'+body['id']).json()['state'],'published')
        again=self.client.post(self.base+'/'+body['id']+'/transition',json={'state':'deprecated','revision':1,'reason':'stale'})
        self.assertEqual(again.status_code,409)

    def test_invalid_request_is_not_persisted(self):
        for body in ({'version':'../bad','projectRevision':1},{'version':'1.0.0','projectRevision':True},{'version':'1.0.0','projectRevision':999}):
            self.assertIn(self.client.post(self.base,json=body).status_code,(400,409))
        self.assertEqual(self.client.get(self.base).json()['items'],[])
        self.assertEqual(self.client.get(self.base+'?limit=1000').status_code,400)
        self.assertEqual(self.client.get(self.base+'/missing').status_code,404)

    def test_generated_models_accept_actual_response(self):
        from api_test.generated.models.api_release import ApiRelease
        from api_test.generated.models.api_release_list import ApiReleaseList
        created=self.client.post(self.base,json={'version':'1.0.0','projectRevision':1})
        parsed=ApiRelease.from_dict(created.json());self.assertEqual(parsed.project_revision,1)
        self.assertEqual(len(ApiReleaseList.from_dict(self.client.get(self.base).json()).items),1)

if __name__=='__main__':unittest.main()
