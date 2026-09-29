"""Uses docker-compose.test.yml defaults; FND4_TEST_* overrides take precedence.

Each test creates and removes its own randomly named database. The supplied
connection requires CREATEDB; no existing database tables are changed.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from api_test.cache import RevisionCache
from api_test.collaboration_store import CollaborationStore, RevisionConflictError
from api_test.database import LOCAL_CONTEXT, RequestContext, _pools, connect
from api_test.execution_history import ExecutionHistory
from api_test.load_results import import_k6_result
from api_test.load_test_store import DuplicateRunError, LoadTestStore
from api_test.migrate_postgres import migrate
from api_test.ownership import OwnershipStore

# Test-only defaults: never fall back to STUDIO_DATABASE_URL or production storage.
# Explicit empty values retain an opt-out for intentionally SQLite-only runs.
os.environ.setdefault('FND4_TEST_DATABASE_URL', 'postgresql://studio_test:studio_test_local@127.0.0.1:15432/postgres')
os.environ.setdefault('FND4_TEST_REDIS_URL', 'redis://127.0.0.1:16379/0')


class ProjectionRecoveryTest(unittest.TestCase):
    def test_file_failure_is_committed_and_recoverable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = CollaborationStore(root / 'studio.db', {k: root / k for k in ('projects', 'cases', 'pipelines')})
            store.initialize(False)
            with patch.object(store, '_write_projection', side_effect=OSError('disk full')):
                saved = store.save('projects', 'a.json', {'name': 'committed'})
            self.assertTrue(saved.metadata()['projectionPending'])
            self.assertEqual(store.get('projects', 'a.json').revision, 1)
            with closing(store.connect()) as db:
                self.assertEqual(db.execute('SELECT status FROM projection_jobs').fetchone()[0], 'failed')
            store.repair_projections()
            self.assertEqual(json.loads((root / 'projects/a.json').read_text()), {'name': 'committed'})
            with closing(store.connect()) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM projection_jobs').fetchone()[0], 0)


@unittest.skipUnless(os.environ.get('FND4_TEST_DATABASE_URL'), 'dedicated PostgreSQL URL not supplied')
class PostgresStorageTest(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.conninfo import make_conninfo
        from psycopg import sql
        self.database = 'fnd4_test_' + uuid.uuid4().hex
        self.admin = psycopg.connect(os.environ['FND4_TEST_DATABASE_URL'], autocommit=True)
        self.admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(self.database)))
        self.url = make_conninfo(os.environ['FND4_TEST_DATABASE_URL'], dbname=self.database)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.roots = {k: self.root / k for k in ('projects', 'cases', 'pipelines')}
        self.env = patch.dict(os.environ, {'STUDIO_DATABASE_URL': self.url, 'STUDIO_DATABASE_URL_FILE': '', 'STUDIO_REDIS_URL': ''})
        self.env.start()

    def tearDown(self):
        from psycopg import sql
        pool = _pools.pop(self.url, None)
        if pool:
            pool.close()
        self.env.stop()
        self.temp.cleanup()
        self.admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(self.database)))
        self.admin.close()

    def store(self, context=LOCAL_CONTEXT):
        store = CollaborationStore(self.root / 'unused', self.roots, context=context)
        store.initialize(False)
        return store

    def test_functional_history_details_search_and_restart(self):
        history = ExecutionHistory(self.root / 'unused')
        stamp = datetime.now(timezone.utc).isoformat()
        history.record(run_id='functional_100%', started_at=stamp, finished_at=stamp,
                       duration_ms=5, status='failed', exit_code=1, projects=['a.json'],
                       targets=[{'kind': 'case', 'reference': 'tag/api/a.json'}], environment='qa',
                       report={'targets': [{'target': 'tag/api/a.json', 'status': 'failed',
                               'assertions': [{'index': 1, 'passed': False, 'actual': 'secret-marker'}]}]})
        reopened = ExecutionHistory(self.root / 'unused')
        result = reopened.detail('functional_100%')
        self.assertEqual(result['environment'], 'qa')
        self.assertEqual(result['detail']['outcomes'][0]['assertions'], [{'index': 1, 'passed': False}])
        self.assertNotIn('secret-marker', json.dumps(result))
        self.assertEqual(reopened.dashboard(search='100%')['total'], 1)
        self.assertEqual(reopened.dashboard(search='missing')['total'], 0)
        self.assertEqual(reopened.dashboard(project='a.json')['total'], 1)

    def test_load_results_postgres_import(self):
        fixtures = Path(__file__).parent / 'fixtures' / 'load-tests'
        result = import_k6_result(fixtures / 'smoke-summary.json', fixtures / 'smoke-raw.jsonl')
        repository = LoadTestStore(self.root / 'unused')
        self.assertEqual(repository.import_bundle(result)['id'], result['run']['id'])
        with self.assertRaises(DuplicateRunError):
            repository.import_bundle(result)
        self.assertEqual(repository.detail(result['run']['id'])['summary'], result['summary'])
        self.assertEqual(len(repository.series(result['run']['id'])['items']), 2)
        with closing(connect(self.root / 'unused')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM load_test_thresholds').fetchone()[0], 2)

    def test_load_operations_sql_downsampling_retention_and_portable_restore(self):
        from datetime import timedelta
        from api_test.load_test_benchmark import detailed_fixture
        from api_test.load_test_maintenance import backup, restore, retention_preview, retention_apply, _digest
        from api_test.load_results import _time, _time_text
        from psycopg.conninfo import make_conninfo
        from psycopg import sql
        fixture = detailed_fixture()
        fixture['run']['id'] = 'old-detailed'
        for key in ('startedAt', 'endedAt'):
            fixture['run'][key] = _time_text(_time(fixture['run'][key], key) - timedelta(days=40))
        for point in fixture['series']:
            point['bucketAt'] = _time_text(_time(point['bucketAt'], 'bucketAt') - timedelta(days=40))
        store = LoadTestStore(self.root / 'unused', url=self.url)
        store.import_bundle(fixture)
        store.import_bundle(detailed_fixture())
        series = store.series('old-detailed', max_points=240)
        self.assertEqual(series['sourcePoints'], 2500)
        self.assertLessEqual(len(series['items']), 240)
        self.assertEqual(max(point['p95Ms'] for point in series['items']), 100.)
        self.assertTrue(all(point['memoryMb'] is None for point in series['items']))
        archive = self.root / 'results.jsonl'
        self.assertEqual(backup(store, archive)['runs'], 2)
        restore_name = 'fnd4_restore_' + uuid.uuid4().hex
        self.admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(restore_name)))
        restore_url = make_conninfo(os.environ['FND4_TEST_DATABASE_URL'], dbname=restore_name)
        try:
            self.assertEqual(restore(archive, self.root / 'restore-unused', url=restore_url)['restoredRuns'], 2)
            restored = LoadTestStore(self.root / 'restore-unused', url=restore_url)
            self.assertEqual(restored.detail('old-detailed'), store.detail('old-detailed'))
            self.assertEqual(restored.series('old-detailed', max_points=240), series)
            with self.assertRaisesRegex(ValueError, 'empty'):
                restore(archive, self.root / 'restore-unused', url=restore_url)
        finally:
            pool = _pools.pop(restore_url, None)
            if pool:
                pool.close()
            self.admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(restore_name)))
        manifest = retention_preview(store, now=datetime(2026, 9, 29, tzinfo=timezone.utc))
        self.assertEqual([row['id'] for row in manifest['runs']], ['old-detailed'])
        with store.connection(write=True) as db, db:
            db.execute("UPDATE load_test_series SET p95_ms=p95_ms+1 WHERE run_id='old-detailed'")
        with self.assertRaisesRegex(ValueError, 'stale'):
            retention_apply(store, manifest, confirmation=_digest(manifest))
        manifest = retention_preview(store, now=datetime(2026, 9, 29, tzinfo=timezone.utc))
        self.assertEqual(retention_apply(store, manifest, confirmation=_digest(manifest))['deletedRuns'], 1)
        self.assertIsNone(store.detail('old-detailed'))
        self.assertIsNone(store.detail('bench-detail')['recommendedBaseline'])
        with store.connection() as db:
            for table in ('load_test_thresholds', 'load_test_endpoint_metrics', 'load_test_series'):
                self.assertEqual(db.execute(f"SELECT count(*) FROM {table} WHERE run_id='old-detailed'").fetchone()[0], 0)

    def test_load_restore_refuses_unrelated_user_schema_in_destination(self):
        from api_test.load_test_maintenance import backup, restore
        from api_test.load_test_benchmark import detailed_fixture
        from psycopg.conninfo import make_conninfo
        from psycopg import sql
        import psycopg
        store = LoadTestStore(self.root / 'unused', url=self.url)
        store.import_bundle(detailed_fixture())
        archive = self.root / 'results.jsonl'
        backup(store, archive)
        restore_name = 'fnd4_restore_' + uuid.uuid4().hex
        self.admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(restore_name)))
        restore_url = make_conninfo(os.environ['FND4_TEST_DATABASE_URL'], dbname=restore_name)
        try:
            with psycopg.connect(restore_url) as raw:
                raw.execute('CREATE SCHEMA unrelated')
                raw.execute('CREATE TABLE unrelated.keep(value TEXT)')
                raw.execute("INSERT INTO unrelated.keep VALUES ('preserve')")
            with self.assertRaisesRegex(ValueError, 'empty'):
                restore(archive, self.root / 'restore-unused', url=restore_url)
            with psycopg.connect(restore_url) as raw:
                self.assertEqual(raw.execute('SELECT value FROM unrelated.keep').fetchone()[0], 'preserve')
                self.assertIsNone(raw.execute("SELECT to_regclass('public.load_test_runs')").fetchone()[0])
        finally:
            pool = _pools.pop(restore_url, None)
            if pool:
                pool.close()
            self.admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(restore_name)))

    def test_load_results_sqlite_snapshot_migrates_to_postgres(self):
        from api_test.migrations import migrate_ownership_database
        fixtures = Path(__file__).parent / 'fixtures' / 'load-tests'
        result = import_k6_result(fixtures / 'smoke-summary.json', fixtures / 'smoke-raw.jsonl')
        source = self.root / 'source.db'
        ownership = self.root / 'ownership.db'
        with patch.dict(os.environ, {'STUDIO_DATABASE_URL': '', 'STUDIO_DATABASE_URL_FILE': ''}):
            LoadTestStore(source).import_bundle(result)
            with closing(sqlite3.connect(ownership)) as db:
                migrate_ownership_database(db)
        manifest = migrate(source, ownership, url=self.url)
        self.assertEqual(manifest['load_test_runs']['rows'], 1)
        self.assertEqual(manifest['load_test_series']['rows'], 2)
        self.assertEqual(LoadTestStore(self.root / 'unused').detail(result['run']['id'])['summary'], result['summary'])

    def test_revision_concurrent_write_and_transaction_rollback(self):
        store = self.store()
        store.save('projects', 'a.json', {'name': 'original'})
        def update(number):
            try:
                return store.save('projects', 'a.json', {'name': str(number)}, expected_revision=1).revision
            except RevisionConflictError:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(update, [1, 2])), [2, 'conflict'])
        with closing(store.connect()) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM audit_events').fetchone()[0], 2)
        with patch.object(store, '_queue_projection', side_effect=RuntimeError('rollback')):
            with self.assertRaises(RuntimeError):
                store.save('projects', 'a.json', {'name': 'bad'}, expected_revision=2)
        self.assertEqual(store.get('projects', 'a.json').revision, 2)
        self.assertEqual(len(store.revisions('projects', 'a.json')), 2)

    def test_workspace_membership_actor_and_reference_isolation(self):
        first = self.store()
        first.save('projects', 'same.json', {'name': 'first'}, actor_id='forged')
        with closing(first.connect()) as db, db:
            db.execute("INSERT INTO workspaces(id,name,created_at) VALUES ('second','Second','now')")
            db.execute("INSERT INTO memberships(workspace_id,user_id,role,created_at) VALUES ('second','local-user','editor','now')")
        second = self.store(RequestContext('second', 'local-user'))
        second.save('projects', 'same.json', {'name': 'second'})
        self.assertEqual(first.get('projects', 'same.json').document['name'], 'first')
        self.assertEqual(second.get('projects', 'same.json').document['name'], 'second')
        self.assertEqual(first.revisions('projects', 'same.json')[0]['created_by'], 'local-user')
        with closing(first.connect()) as db, db:
            db.execute("UPDATE memberships SET status='inactive' WHERE workspace_id='second'")
        with self.assertRaises(PermissionError):
            second.get('projects', 'same.json')

    def test_committed_state_survives_projection_failure_and_restart(self):
        store = self.store()
        with patch.object(store, '_write_projection', side_effect=OSError('disk')):
            saved = store.save('projects', 'a.json', {'name': 'db'})
        self.assertTrue(saved.projection_pending)
        self.roots['projects'].mkdir(exist_ok=True)
        (self.roots['projects'] / 'a.json').write_text('{"name":"stale file"}')
        fresh = CollaborationStore(self.root/'unused', self.roots)
        fresh.initialize(True)
        self.assertEqual(fresh.get('projects', 'a.json').document, {'name': 'db'})
        self.assertEqual(json.loads((self.roots['projects']/'a.json').read_text()), {'name': 'db'})
        fresh.delete('projects', 'a.json')
        fresh.initialize(True)
        self.assertIsNone(fresh.get('projects', 'a.json'))

    def test_execution_metadata_filter_pagination_and_ownership(self):
        self.store()
        history = ExecutionHistory(self.root/'unused')
        now = datetime.now(timezone.utc).isoformat()
        for index in range(23):
            history.record(run_id=str(index), started_at=now, finished_at=now, duration_ms=1.2,
                           status='passed', exit_code=0, projects=['p.json'], targets=[])
        dashboard = history.dashboard(project='p.json', page=2)
        self.assertEqual(dashboard['summary']['passed'], 23)
        self.assertEqual(len(dashboard['items']), 3)
        self.assertEqual(history.dashboard(project='unknown')['total'], 0)
        ownership = OwnershipStore(self.root/'no-sqlite')
        document = {'base_url': 'https://example.com'}
        ownership.issue('p.json', document, 'https://example.com', 'session')
        self.assertEqual(len(ownership.status('p.json', document)['proofs']), 1)
        ownership.revoke('p.json')
        self.assertEqual(ownership.status('p.json', document)['proofs'][0]['state'], 'revoked')
        ownership.grant('p.json', 'https://other.example/a', 'GET')
        with closing(connect(self.root/'unused')) as db, db:
            db.execute("INSERT INTO workspaces(id,name,created_at) VALUES ('other','Other','now')")
            db.execute("INSERT INTO memberships(workspace_id,user_id,role,created_at) VALUES ('other','local-user','owner','now')")
        other = OwnershipStore(context=RequestContext('other', 'local-user'))
        self.assertEqual(other.status('p.json', document)['proofs'], [])
        self.assertEqual(other.status('p.json', document)['grants'], [])
        ownership.authorize('p.json', document, 'https://other.example/a', 'GET', external=True)
        ownership.revoke('p.json', remove=True)
        self.assertEqual(ownership.status('p.json', document)['grants'], [])

    def test_audit_append_only_and_viewer_write_denial(self):
        import psycopg
        store = self.store()
        store.save('projects', 'a.json', {'name': 'original'})
        with self.assertRaises(psycopg.errors.RaiseException):
            with closing(store.connect()) as db, db:
                db.execute("DELETE FROM audit_events")
        with closing(store.connect()) as db, db:
            self.assertTrue(db.execute('SELECT request_id FROM audit_events').fetchone()[0])
            db.execute("UPDATE memberships SET role='viewer' WHERE workspace_id='default'")
        self.assertIsNotNone(store.get('projects', 'a.json'))
        with self.assertRaises(PermissionError):
            store.save('projects', 'a.json', {'name': 'bad'}, expected_revision=1)
        self.assertEqual(store.get('projects', 'a.json').revision, 1)

    def test_legacy_history_requires_explicit_import(self):
        self.source()
        store = CollaborationStore(self.root/'source.db', self.roots)
        from api_test.collaboration_store import CollaborationStoreError
        with self.assertRaisesRegex(CollaborationStoreError, '먼저 이관'):
            store.initialize(True)
        with closing(connect(self.root/'unused')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM documents').fetchone()[0], 0)

    def test_repair_command_recreates_lost_projection_without_new_revision(self):
        from api_test.repair_projections import main
        store = self.store()
        first = store.save('projects', 'a.json', {'name': 'db'})
        (self.roots['projects']/'a.json').unlink()
        with patch('sys.argv', ['repair_projections', '--root', str(self.root), '--all']):
            main()
        self.assertEqual(json.loads((self.roots['projects']/'a.json').read_text()), {'name': 'db'})
        self.assertEqual(store.get('projects', 'a.json').revision, first.revision)

    def source(self):
        with patch.dict(os.environ, {'STUDIO_DATABASE_URL': '', 'STUDIO_DATABASE_URL_FILE': ''}):
            source = CollaborationStore(self.root/'source.db', self.roots)
            source.initialize(False)
            first = source.save('projects', 'a.json', {'name': 'one'})
            source.save('projects', 'a.json', {'name': 'two'}, expected_revision=1)
            source.delete('projects', 'a.json')
            ownership = OwnershipStore(self.root/'ownership.db')
            ownership.issue('a.json', {'base_url': 'https://example.com'}, 'https://example.com', 's')
        return first

    def test_snapshot_import_idempotency_and_soft_delete(self):
        first = self.source()
        before = (self.root/'source.db').read_bytes()
        manifest = migrate(self.root/'source.db', self.root/'ownership.db')
        self.assertEqual(manifest, migrate(self.root/'source.db', self.root/'ownership.db'))
        self.assertEqual(before, (self.root/'source.db').read_bytes())
        store = self.store()
        self.assertIsNone(store.get('projects', 'a.json'))
        stored = store.get('projects', 'a.json', include_deleted=True)
        self.assertEqual((stored.document_id, stored.revision), (first.document_id, 2))
        self.assertEqual(len(store.revisions('projects', 'a.json')), 2)
        self.assertEqual(len(OwnershipStore().status('a.json', {'base_url':'https://example.com'})['proofs']), 1)

    def test_snapshot_import_replaces_only_empty_bootstrap_context(self):
        self.source()
        self.store()  # Simulate the API starting before the offline migration.
        manifest = migrate(self.root/'source.db', self.root/'ownership.db')
        self.assertGreater(manifest['documents']['rows'], 0)
        self.assertIsNotNone(self.store().get('projects', 'a.json', include_deleted=True))

    def test_migration_bad_hash_rolls_back_all_data(self):
        self.source()
        with closing(sqlite3.connect(self.root/'source.db')) as db, db:
            db.execute("UPDATE document_revisions SET content_hash='bad' WHERE revision=1")
        with self.assertRaisesRegex(ValueError, 'content hash'):
            migrate(self.root/'source.db', self.root/'ownership.db')
        with closing(connect(self.root/'unused')) as db, db:
            self.assertEqual(db.execute('SELECT count(*) FROM documents').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM proofs').fetchone()[0], 0)

    def test_migration_conflicting_destination_rolls_back(self):
        self.source()
        store = self.store()
        store.save('projects', 'destination.json', {'name': 'keep'})
        with self.assertRaisesRegex(ValueError, 'destination differs'):
            migrate(self.root/'source.db', self.root/'ownership.db')
        self.assertEqual(store.list_references('projects'), ['destination.json'])

    @unittest.skipUnless(os.environ.get('FND4_TEST_REDIS_URL'), 'dedicated Redis URL not supplied')
    def test_redis_hit_miss_expiry_invalidation_and_outage(self):
        from redis import Redis
        client = Redis.from_url(os.environ['FND4_TEST_REDIS_URL'], decode_responses=True)
        store = self.store()
        store.cache = RevisionCache(client, ttl=1)
        saved = store.save('projects', 'a.json', {'name': 'one', 'secret': 'never-cache-this'})
        key = store.cache.key(store.context.workspace_id, saved.document_id, 1)
        self.assertIsNone(client.get(key))
        expected = store.revisions('projects', 'a.json')
        self.assertEqual(store.cache.get(key), expected)
        self.assertNotIn('never-cache-this', client.get(key))
        client.set(key, json.dumps(expected), ex=1)
        self.assertEqual(store.revisions('projects', 'a.json'), expected)
        time.sleep(1.1)
        self.assertIsNone(store.cache.get(key))
        store.revisions('projects', 'a.json')
        store.save('projects', 'a.json', {'name': 'two'}, expected_revision=1)
        self.assertIsNone(client.get(key))
        from redis.exceptions import ConnectionError
        with patch.object(client, 'get', side_effect=ConnectionError), patch.object(client, 'set', side_effect=ConnectionError), patch.object(client, 'delete', side_effect=ConnectionError):
            self.assertEqual(len(store.revisions('projects', 'a.json')), 2)
            store.save('projects', 'a.json', {'name': 'three'}, expected_revision=2)
        self.assertEqual(len(store.revisions('projects', 'a.json')), 3)
        client.delete(store.cache.key(store.context.workspace_id, saved.document_id, 3))
        client.close()

# Replay the complete existing HTTP matrix against both fresh and imported PG.
import test_asgi_contract as http_contract


@unittest.skipUnless(os.environ.get('FND4_TEST_DATABASE_URL'), 'dedicated PostgreSQL URL not supplied')
class PostgresHttpContractTest(http_contract.AsgiContractTest):
    def setUp(self):
        PostgresStorageTest.setUp(self)
        http_contract.AsgiContractTest.setUp(self)

    def tearDown(self):
        self.doCleanups()
        PostgresStorageTest.tearDown(self)


@unittest.skipUnless(os.environ.get('FND4_TEST_DATABASE_URL'), 'dedicated PostgreSQL URL not supplied')
class ImportedPostgresHttpContractTest(PostgresHttpContractTest):
    def setUp(self):
        PostgresStorageTest.setUp(self)
        PostgresStorageTest.source(self)
        migrate(self.root/'source.db', self.root/'ownership.db')
        http_contract.AsgiContractTest.setUp(self)
