import os
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch

from api_test.collaboration_store import CollaborationStore
from api_test.project_listing import list_project_page


def exercise_pages(test, store):
    refs = [f'project-{n:02}.json' for n in range(13)]
    for index, ref in enumerate(refs):
        store.save('projects', ref, {'name': '한글 서비스' if index == 5 else f'Project {index}', 'base_url': 'https://example.test', 'secret': 'must-not-leak'})
    for sort, expected in [('reference_asc', refs), ('reference_desc', refs[::-1]), ('created_desc', refs[::-1])]:
        pages = []; cursor = ''; seen = []
        while True:
            page = list_project_page(store, page_size='5', sort=sort, cursor=cursor)
            test.assertLessEqual(len(page['items']), 5)
            test.assertNotIn('must-not-leak', str(page))
            seen.extend(page['items']); pages.append(page)
            cursor = page['nextCursor']
            if not cursor: break
        test.assertEqual(seen, expected)
        test.assertIsNone(pages[0]['previousCursor'])
        for index in range(len(pages)-1, 0, -1):
            page = list_project_page(store, page_size='5', sort=sort, cursor=pages[index]['previousCursor'])
            test.assertEqual(page['items'], pages[index-1]['items'])
    test.assertEqual(list_project_page(store, search='한글')['items'], [refs[5]])
    test.assertEqual(list_project_page(store, search='PROJECT-02')['items'], [refs[2]])
    store.save('projects', 'literal.json', {'name': '100%_! literal'})
    test.assertEqual(list_project_page(store, search='%_!')['items'], ['literal.json'])
    first = list_project_page(store, page_size='2')
    for kwargs in [{'search': 'new'}, {'sort': 'reference_desc'}, {'page_size': '3'}, {'include_example': False}]:
        with test.assertRaises(ValueError):
            list_project_page(store, **{'page_size': '2', 'cursor': first['nextCursor'], **kwargs})


class ProjectListingTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.dict(os.environ, {'STUDIO_DATABASE_URL': '', 'STUDIO_DATABASE_URL_FILE': '', 'STUDIO_REDIS_URL': ''}))
        self.store = CollaborationStore(self.root/'studio.db', {k: self.root/k for k in ('projects', 'cases', 'pipelines')})
        self.store.initialize(False)

    def test_sqlite_bidirectional_pages_search_and_conditions(self):
        exercise_pages(self, self.store)

    def test_deletions_and_inserts_do_not_shift_keyset(self):
        for ref in ['a.json','b.json','c.json','d.json','e.json']:
            self.store.save('projects',ref,{'name':ref})
        page = list_project_page(self.store, page_size='2')
        self.store.delete('projects','b.json')
        self.store.save('projects','aa.json',{'name':'new'})
        next_page = list_project_page(self.store, page_size='2',cursor=page['nextCursor'])
        self.assertEqual(next_page['items'],['c.json','d.json'])
        self.assertEqual(list_project_page(self.store,page_size='2',cursor=next_page['nextCursor'])['items'],['e.json'])

    def test_created_timestamp_ties_use_reference(self):
        for ref in ['b.json','a.json','c.json']:
            self.store.save('projects',ref,{'name':ref})
        with closing(self.store.connect()) as db, db:
            db.execute("UPDATE documents SET created_at = ?", ('2026-01-01',))
        page=list_project_page(self.store,page_size='2',sort='created_desc')
        self.assertEqual(page['items'],['c.json','b.json'])
        self.assertEqual(list_project_page(self.store,page_size='2',sort='created_desc',cursor=page['nextCursor'])['items'],['a.json'])

    def test_invalid_inputs_and_example_filter(self):
        for size in ['0','101','-1','1.5','abc','９','']:
            with self.assertRaises(ValueError):list_project_page(self.store,page_size=size)
        for cursor in ['!', 'e30=', 'x'*4097]:
            with self.assertRaises(ValueError):list_project_page(self.store,cursor=cursor)
        self.store.save('projects','example-api.json',{'name':'Example'})
        self.assertEqual(list_project_page(self.store,include_example=False)['items'],[])
        self.assertEqual(len(list_project_page(self.store)['items']),1)


class ProjectPageHttpTest(unittest.TestCase):
    def setUp(self):
        import test_workspace_isolation
        test_workspace_isolation.WorkspaceIsolationTest.setUp(self)

    def test_workspace_cursor_and_legacy_contract(self):
        for n in range(4):
            self.stores['team-a'].save('projects',f'a{n}.json',{'name':f'A {n}'})
        def get(params, principal='team-a-owner'):
            return self.client.get('/api/projects',params=params,headers={'test-principal':principal})
        page=get({'page_size':2})
        self.assertEqual(page.status_code,200,page.text)
        self.assertEqual(len(page.json()['items']),2)
        cursor=page.json()['nextCursor']
        self.assertEqual(get({'page_size':2,'cursor':cursor},'team-b-owner').status_code,400)
        self.assertEqual(get({'page_size':2},'team-b-owner').json()['items'],['same.json'])
        self.assertEqual(len(get({}).json()['items']),5)
        for params in [{'page_size':'0'},{'sort':'DROP TABLE documents'},{'q':'x'*101},{'cursor':'invalid'}]:
            self.assertEqual(get(params).status_code,400)
        with patch.object(self.stores['team-a'].__class__, 'list_references', side_effect=AssertionError('unbounded list')), patch.object(self.stores['team-a'].__class__, 'get', side_effect=AssertionError('per-document read')):
            self.assertEqual(get({'page_size':2}).status_code,200)
