"""Explicit personal snapshots, separate from metadata-only execution history."""
import json
from api_test.database import require_membership
from api_test.reports import now


class SavedResults:
    def __init__(self, history):
        self.history = history
        self.context = history.context

    @property
    def scope(self):
        return (self.context.workspace_id, self.context.user_id)

    def get(self, run_id):
        with self.history.connect() as connection:
            row = connection.execute("""SELECT snapshot, saved_at FROM saved_run_results
                WHERE workspace_id = ? AND user_id = ? AND run_id = ?""", (*self.scope, run_id)).fetchone()
        return {**json.loads(row['snapshot']), 'savedAt': row['saved_at']} if row else None

    def save(self, job):
        saved_at = now()
        with self.history.connect() as connection:
            if require_membership(connection, self.context) not in ('owner', 'admin', 'editor', 'runner'):
                raise PermissionError('Execution role required')
            connection.execute("""INSERT INTO saved_run_results
                (workspace_id, user_id, run_id, project_reference, case_reference, saved_at, status, snapshot)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id, user_id, run_id) DO NOTHING""",
                (*self.scope, job['runId'], job['project'], job['caseReference'], saved_at,
                 job['status'], json.dumps(job, ensure_ascii=False)))
        return self.get(job['runId'])

    def list(self, project, reference):
        with self.history.connect() as connection:
            rows = connection.execute("""SELECT run_id, saved_at, status FROM saved_run_results
                WHERE workspace_id = ? AND user_id = ? AND project_reference = ? AND case_reference = ?
                ORDER BY saved_at DESC, run_id DESC LIMIT 100""", (*self.scope, project, reference)).fetchall()
        return [{'runId': row['run_id'], 'savedAt': row['saved_at'], 'status': row['status']} for row in rows]
