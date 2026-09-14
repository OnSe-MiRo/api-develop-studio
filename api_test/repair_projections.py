"""Rebuild pending (or all) CLI JSON projections from committed database state."""
import argparse
import os
from contextlib import closing
from pathlib import Path

from api_test.collaboration_store import CollaborationStore
from api_test.database import LOCAL_CONTEXT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--all', action='store_true', help='also rebuild projections after volume loss/restore')
    args = parser.parse_args()
    root = args.root.resolve()
    store = CollaborationStore(Path(os.environ.get('STUDIO_DB_PATH', root/'data/studio.db')),
                               {'projects': root/'projects', 'cases': root/'case', 'pipelines': root/'pipelines'},
                               context=LOCAL_CONTEXT)
    store.initialize(import_existing=False)
    if args.all:
        with closing(store.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("INSERT INTO projection_jobs(document_id,revision) SELECT id,current_revision FROM documents "
                       "WHERE workspace_id=? ON CONFLICT(document_id) DO UPDATE SET revision=excluded.revision,status='pending'",
                       (store.context.workspace_id,))
    if store.repair_projections():
        raise SystemExit('Projection recovery incomplete; inspect storage permissions/capacity and retry.')
    print('Projection recovery complete.')


if __name__ == '__main__':
    main()
