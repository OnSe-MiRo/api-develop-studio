import os
import tempfile
import time
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch

from api_test.collaboration_store import CollaborationStore
from api_test.document_listing import list_document_page
from api_test.project_listing import list_project_page


def cases(store, **kwargs):
    return list_document_page(store, kind='cases', project='one.json', sort='name_asc', **kwargs)


def exercise_case_pages(test, store):
    refs = [f'{"beta" if n % 2 else "alpha"}/api-{n % 3}/case-{n:02}.json' for n in range(13)]
    store.save('projects', 'one.json', {'name': 'One'})
    store.save('projects', 'two.json', {'name': 'Two'})
    for index, ref in enumerate(refs):
        store.save('cases', ref, {'project':'one.json', 'name':'한글 검색' if index == 5 else f'Case {index}', 'request':{'url':'/test', 'headers':{'Authorization':'PRIVATE'}}, 'expected':{'body':{'secret':'PRIVATE'}}})
    store.save('cases','other/api/case-00.json',{'project':'two.json','request':{'url':'/other'}})
    for sort, expected in [('name_asc', refs), ('name_desc', refs[::-1]), ('created_desc', refs[::-1])]:
        cursor=''; pages=[]; seen=[]
        while True:
            page=list_document_page(store,kind='cases',project='one.json',page_size='5',sort=sort,cursor=cursor)
            test.assertLessEqual(len(page['items']),5);test.assertNotIn('PRIVATE',str(page))
            pages.append(page);seen.extend(page['items']);cursor=page['nextCursor']
            if not cursor:break
        test.assertEqual(seen,expected)
        for index in range(len(pages)-1,0,-1):
            previous=list_document_page(store,kind='cases',project='one.json',page_size='5',sort=sort,cursor=pages[index]['previousCursor'])
            test.assertEqual(previous['items'],pages[index-1]['items'])
    test.assertEqual(cases(store,search='한글')['items'],[refs[5]])
    test.assertEqual(cases(store,search='API-2')['items'],[ref for ref in refs if '/api-2/' in ref])
    test.assertEqual(cases(store,tag='alpha')['items'],[ref for ref in refs if ref.startswith('alpha/')])
    test.assertEqual(cases(store,tag='Alpha')['items'],[])
    test.assertEqual(cases(store,tag='alp')['items'],[])
    test.assertEqual(cases(store,tag='beta',search='api-1')['items'],[ref for ref in refs if ref.startswith('beta/') and '/api-1/' in ref])
    first=cases(store,page_size='2')
    for overrides in [{'project':'two.json'}, {'tag':'alpha'}, {'search':'Case'}, {'sort':'name_desc'}, {'page_size':'3'}]:
        with test.assertRaises(ValueError):
            list_document_page(store,**{'kind':'cases','project':'one.json','sort':'name_asc','page_size':'2','cursor':first['nextCursor'],**overrides})
    test.assertEqual(len(store.list_references('cases','one.json')),13)


class CaseListingTest(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.dict(os.environ,{'STUDIO_DATABASE_URL':'','STUDIO_DATABASE_URL_FILE':'','STUDIO_REDIS_URL':''}))
        self.store=CollaborationStore(self.root/'studio.db',{k:self.root/k for k in ('projects','cases','pipelines')})
        self.store.initialize(False)

    def test_pages_filters_and_project_scope(self):
        exercise_case_pages(self,self.store)

    def test_ties_deletion_and_insertion_keep_stable_order(self):
        for ref in ['a/api/same.json','b/api/same.json','c/api/same.json']:
            self.store.save('cases',ref,{'project':'one.json'})
        with closing(self.store.connect()) as db,db:db.execute('UPDATE documents SET created_at=?',('2026-01-01',))
        page=cases(self.store,page_size='2')
        self.assertEqual(page['items'],['a/api/same.json','b/api/same.json'])
        self.store.delete('cases','b/api/same.json')
        self.store.save('cases','aa/api/same.json',{'project':'one.json'})
        self.assertEqual(cases(self.store,page_size='2',cursor=page['nextCursor'])['items'],['c/api/same.json'])
        self.assertEqual(list_document_page(self.store,kind='cases',project='one.json',sort='created_desc',page_size='2')['items'],['aa/api/same.json','c/api/same.json'])

    def test_wildcards_invalid_input_and_cross_kind_cursor(self):
        self.store.save('cases','tag/api/test.json',{'project':'one.json','name':'100%_!'})
        self.assertEqual(cases(self.store,search='%_!')['items'],['tag/api/test.json'])
        for options in [{'project':''},{'tag':'a/b'},{'tag':'x'*129},{'search':'x'*101},{'sort':'bad'},{'page_size':'0'},{'cursor':'invalid'}]:
            with self.assertRaises(ValueError):
                list_document_page(self.store,**{'kind':'cases','project':'one.json','sort':'name_asc',**options})
        for ref in ['a.json','b.json']:self.store.save('projects',ref,{'name':ref})
        cursor=list_project_page(self.store,page_size='1')['nextCursor']
        with self.assertRaises(ValueError):cases(self.store,page_size='1',cursor=cursor)


class CasePageHttpTest(unittest.TestCase):
    def setUp(self):
        import test_workspace_isolation
        test_workspace_isolation.WorkspaceIsolationTest.setUp(self)

    def test_unpaged_list_reads_only_changed_sqlite_files_and_preserves_workspace_scope(self):
        def listing(workspace='team-a'):
            response = self.client.get('/api/cases', params={'project': 'same.json'},
                                       headers={'test-principal': workspace + '-owner'})
            self.assertEqual(response.status_code, 200)
            return response.json()

        # Model settled projections for the read-count checks without a wall-clock sleep.
        clock = self.enterContext(patch('api_test.case_projection.time_ns', side_effect=lambda: time.time_ns() + 3_000_000_000))
        extra = 'tag/api/second.json'
        shared = 'tag/api/same.json'
        store = self.stores['team-a']
        store.save('cases', extra, {'project': 'same.json', 'request': {'url': '/two', 'headers': {'X-Private': 'hidden'}}})
        self.stores['team-b'].save('cases', shared, {'project': 'same.json', 'request': {'url': '/team-b'}}, expected_revision=1)
        expected = {'items': [shared, extra], 'details': {shared: {'url': '/echo'}, extra: {'url': '/two'}}}
        self.assertEqual(listing(), expected)
        store.save('projects', 'other.json', {'name': 'Other'})
        store.save('cases', 'other/api/only.json', {'project': 'other.json', 'request': []})
        response = self.client.get('/api/cases', headers={'test-principal': 'team-a-owner'})
        self.assertEqual(response.json()['items'], ['other/api/only.json', shared, extra])
        self.assertEqual(response.json()['details']['other/api/only.json'], {'url': ''})
        empty = self.client.get('/api/cases', params={'project': 'missing.json'}, headers={'test-principal': 'team-a-owner'})
        self.assertEqual(empty.json(), {'items': [], 'details': {}})
        reads = []
        original_open = Path.open
        def observe(path, *args, **kwargs):
            if path.suffix == '.json' and 'cases' in path.parts:
                reads.append(path)
            return original_open(path, *args, **kwargs)

        with patch.object(Path, 'open', observe):
            self.assertEqual(listing(), expected)
            self.assertEqual(listing('team-b')['details'][shared], {'url': '/team-b'})
            reads.clear()
            self.assertEqual(listing(), expected)
            self.assertEqual(reads, [] if os.name == 'posix' else [store.roots['cases'] / r for r in (shared, extra)])
        path = store.roots['cases'] / extra
        stamp = path.stat()
        payload = path.read_text(encoding='utf-8').replace('/two', '/new')
        replacement = path.with_suffix('.new')
        replacement.write_text(payload, encoding='utf-8')
        os.utime(replacement, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        replacement.replace(path)
        expected['details'][extra] = {'url': '/new'}
        reads.clear()
        with patch.object(Path, 'open', observe):
            self.assertEqual(listing(), expected)
            self.assertEqual(reads, [path] if os.name == 'posix' else [store.roots['cases'] / shared, path])
        # An in-place edit can preserve both size and mtime, including on coarse filesystems.
        clock.side_effect = None
        clock.return_value = time.time_ns()
        path.write_text(payload.replace('/new', '/now'), encoding='utf-8')
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        expected['details'][extra] = {'url': '/now'}
        self.assertEqual(listing(), expected)
        updated = store.save('cases', extra, {'project': 'same.json', 'request': {'url': 7}}, expected_revision=1)
        self.assertEqual(updated.revision, 2)
        self.assertEqual(listing()['details'][extra], {'url': ''})
        store.delete('cases', extra)
        self.assertEqual(listing(), {'items': [shared], 'details': {shared: {'url': '/echo'}}})

    def test_workspace_project_input_and_legacy_contract(self):
        for n in range(4):self.stores['team-a'].save('cases',f'tag/api/c{n}.json',{'project':'same.json','request':{'url':'/test'}})
        self.stores['team-a'].save('projects','other.json',{'name':'Other'})
        self.stores['team-a'].save('cases','tag/api/hidden.json',{'project':'other.json'})
        def get(params,user='team-a-owner'):
            return self.client.get('/api/cases',params=params,headers={'test-principal':user})
        page=get({'project':'same.json','page_size':2})
        self.assertEqual(page.status_code,200,page.text)
        self.assertEqual(page.json()['items'],['tag/api/c0.json','tag/api/c1.json'])
        self.assertEqual(get({'project':'same.json','page_size':2,'cursor':page.json()['nextCursor']},'team-b-owner').status_code,400)
        self.assertEqual(get({'project':'same.json','page_size':2},'team-b-owner').json()['items'],['tag/api/same.json'])
        self.assertEqual(len(get({'project':'same.json'}).json()['items']),5)
        self.assertEqual(get({'page_size':2}).status_code,400)
        self.assertNotEqual(get({'project':'missing.json','page_size':2}).status_code,200)
        with patch.object(CollaborationStore,'list_references',side_effect=AssertionError('unbounded query')):
            self.assertEqual(get({'project':'same.json','page_size':2}).status_code,200)
