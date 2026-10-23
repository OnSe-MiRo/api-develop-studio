import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from api_test.collaboration_store import CollaborationStore
from api_test.document_listing import list_document_page

def exercise_pipeline_pages(test, store):
    refs = [f'project-{n:02}.json' for n in range(13)]
    for index, ref in enumerate(refs):
        store.save('pipelines', ref, {'project': 'one.json', 'steps': [{'token': 'PRIVATE'}], 'name': '한글 서비스' if index == 5 else f'Project {index}', 'base_url': 'https://example.test', 'secret': 'must-not-leak'})
    for sort, expected in [('reference_asc', refs), ('reference_desc', refs[::-1]), ('created_desc', refs[::-1])]:
        pages = []; cursor = ''; seen = []
        while True:
            page = list_document_page(store, kind='pipelines', project='one.json', page_size='5', sort=sort, cursor=cursor)
            test.assertLessEqual(len(page['items']), 5)
            test.assertNotIn('must-not-leak', str(page))
            seen.extend(page['items']); pages.append(page)
            cursor = page['nextCursor']
            if not cursor: break
        test.assertEqual(seen, expected)
        test.assertIsNone(pages[0]['previousCursor'])
        for index in range(len(pages)-1, 0, -1):
            page = list_document_page(store, kind='pipelines', project='one.json', page_size='5', sort=sort, cursor=pages[index]['previousCursor'])
            test.assertEqual(page['items'], pages[index-1]['items'])
    test.assertEqual(list_document_page(store, kind='pipelines', project='one.json', search='한글')['items'], [refs[5]])
    test.assertEqual(list_document_page(store, kind='pipelines', project='one.json', search='PROJECT-02')['items'], [refs[2]])
    store.save('pipelines', 'literal.json', {'project': 'one.json', 'steps': [{'token': 'PRIVATE'}], 'name': '100%_! literal'})
    test.assertEqual(list_document_page(store, kind='pipelines', project='one.json', search='%_!')['items'], ['literal.json'])
    first = list_document_page(store, kind='pipelines', project='one.json', page_size='2')
    for kwargs in [{'search': 'new'}, {'sort': 'reference_desc'}, {'page_size': '3'}, {'search':'changed'}]:
        with test.assertRaises(ValueError):
            list_document_page(store, **{'kind':'pipelines','project':'one.json','page_size': '2', 'cursor': first['nextCursor'], **kwargs})


class PipelineListingTest(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.dict(os.environ,{'STUDIO_DATABASE_URL':'','STUDIO_DATABASE_URL_FILE':'','STUDIO_REDIS_URL':''}))
        self.store=CollaborationStore(self.root/'db',{k:self.root/k for k in ('projects','cases','pipelines')})
        self.store.initialize(False)

    def test_pages_search_sort_and_content_minimization(self):
        exercise_pipeline_pages(self,self.store)
        self.assertEqual(list_document_page(self.store,kind='pipelines',project='two.json')['items'],[])
        self.assertNotIn('PRIVATE',str(list_document_page(self.store,kind='pipelines',project='one.json')))

    def test_deletion_and_insert_preserve_boundary(self):
        for ref in ['a.json','b.json','c.json','d.json']:
            self.store.save('pipelines',ref,{'project':'one.json'})
        first=list_document_page(self.store,kind='pipelines',project='one.json',page_size='2')
        self.store.delete('pipelines','b.json')
        self.store.save('pipelines','aa.json',{'project':'one.json'})
        second=list_document_page(self.store,kind='pipelines',project='one.json',page_size='2',cursor=first['nextCursor'])
        self.assertEqual(second['items'],['c.json','d.json'])
        with self.assertRaises(ValueError):
            list_document_page(self.store,kind='pipelines',project='two.json',page_size='2',cursor=first['nextCursor'])
        for options in [{'page_size':'101'},{'sort':'bad'},{'search':'x'*101},{'cursor':'!'},{'project':''}]:
            with self.assertRaises(ValueError):
                list_document_page(self.store,**{'kind':'pipelines','project':'one.json',**options})

class PipelinePageHttpTest(unittest.TestCase):
    def setUp(self):
        import test_workspace_isolation
        test_workspace_isolation.WorkspaceIsolationTest.setUp(self)

    def test_workspace_project_and_legacy_boundaries(self):
        for workspace in ['team-a','team-b']:
            for n in range(3):self.stores[workspace].save('pipelines',f'p{n}.json',{'project':'same.json','steps':[{'private':'SECRET'}]})
        self.stores['team-a'].save('projects','other.json',{'name':'Other'})
        self.stores['team-a'].save('pipelines','other.json',{'project':'other.json'})
        def get(params,user='team-a-owner'):
            return self.client.get('/api/pipelines',params=params,headers={'test-principal':user})
        first=get({'project':'same.json','page_size':2});self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json()['items'],['p0.json','p1.json']);self.assertNotIn('SECRET',first.text)
        self.assertEqual(get({'project':'same.json','page_size':2,'cursor':first.json()['nextCursor']},'team-b-owner').status_code,400)
        self.assertEqual(get({'project':'other.json','page_size':2}).json()['items'],['other.json'])
        self.assertEqual(len(get({'project':'same.json'}).json()['items']),3)
        self.assertEqual(get({'page_size':2}).status_code,400)
        with patch.object(CollaborationStore,'list_references',side_effect=AssertionError('unbounded')):
            self.assertEqual(get({'project':'same.json','page_size':2}).status_code,200)
