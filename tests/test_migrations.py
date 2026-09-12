from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from api_test.migrations import Migration, MigrationRunner, migrate_studio_database


class MigrationRunnerTest(unittest.TestCase):
    def connect(self, root: str) -> sqlite3.Connection:
        return sqlite3.connect(Path(root) / "studio.db")

    def test_empty_database_reaches_latest_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory, closing(self.connect(directory)) as connection:
            version = migrate_studio_database(connection)

            self.assertEqual(version, 2)
            self.assertEqual(
                [row[0] for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")],
                [1, 2],
            )
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"documents", "document_revisions", "executions"}.issubset(tables))

    def test_existing_unversioned_database_is_adopted_without_data_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory, closing(self.connect(directory)) as connection:
            connection.execute(
                """CREATE TABLE executions (
                    run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
                    duration_ms REAL NOT NULL, status TEXT NOT NULL, exit_code INTEGER,
                    projects TEXT NOT NULL, targets TEXT NOT NULL)"""
            )
            connection.execute(
                "INSERT INTO executions VALUES ('run-1', 'a', 'b', 1, 'passed', 0, '[]', '[]')"
            )
            connection.commit()

            migrate_studio_database(connection)

            self.assertEqual(connection.execute("SELECT run_id FROM executions").fetchone()[0], "run-1")
            self.assertEqual(connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 2)

    def test_failure_rolls_back_schema_and_version_rows(self) -> None:
        def first(connection: sqlite3.Connection) -> None:
            connection.execute("CREATE TABLE first_change (id INTEGER)")

        def broken(connection: sqlite3.Connection) -> None:
            connection.execute("CREATE TABLE second_change (id INTEGER)")
            raise RuntimeError("migration failed")

        runner = MigrationRunner((Migration(1, "first", first), Migration(2, "broken", broken)))
        with tempfile.TemporaryDirectory() as directory, closing(self.connect(directory)) as connection:
            with self.assertRaisesRegex(RuntimeError, "migration failed"):
                runner.run(connection)

            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn("first_change", tables)
            self.assertNotIn("second_change", tables)
            self.assertNotIn("schema_migrations", tables)

    def test_rejects_gapped_versions(self) -> None:
        with self.assertRaisesRegex(ValueError, "consecutive"):
            MigrationRunner((Migration(2, "late", lambda connection: None),))


if __name__ == "__main__":
    unittest.main()
