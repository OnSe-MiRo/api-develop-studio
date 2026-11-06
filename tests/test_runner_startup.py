"""A plain SQLite runner should load optional backends only when it uses them."""
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class RunnerStartupTests(unittest.TestCase):
    def test_plain_sqlite_cli_does_not_initialize_postgres_or_fernet(self):
        probe = textwrap.dedent("""
            import runpy, sqlite3, sys
            from pathlib import Path
            from api_test import database
            with database.connect(Path(sys.argv.pop()), url='') as db:
                assert db.execute('SELECT 1').fetchone()[0] == 1
            sys.argv = ['run_api_tests.py', '--help']
            try:
                runpy.run_path(sys.argv[0], run_name='__main__')
            except SystemExit as exit_status:
                assert exit_status.code == 0
            unwanted = {'psycopg', 'psycopg_pool', 'cryptography.fernet'} & sys.modules.keys()
            assert not unwanted, sorted(unwanted)
            from api_test.database import DATABASE_ERRORS
            assert isinstance(sqlite3.OperationalError(), DATABASE_ERRORS)
            try:
                import psycopg, psycopg_pool
            except ImportError:
                pass
            else:
                assert isinstance(psycopg.OperationalError(), DATABASE_ERRORS)
                assert isinstance(psycopg_pool.PoolTimeout(), DATABASE_ERRORS)
        """)
        with tempfile.TemporaryDirectory() as root:
            run = subprocess.run([sys.executable, '-c', probe, str(Path(root) / 'probe.db')],
                                 cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=20)
        self.assertEqual(run.returncode, 0, run.stderr)
