"""Small request fixture; every send traverses the real FastAPI TestClient."""
from fastapi.testclient import TestClient
from react_server import app
from contextlib import closing
from pathlib import Path
import os
from api_test.database import connect, initialize_local_context
from api_test.migrations import migrate_studio_database


def prepare_local_identity():
    import react_server as studio
    path = Path(os.environ.get('STUDIO_DB_PATH', studio.ROOT / 'data' / 'studio.db'))
    with closing(connect(path)) as db, db:
        migrate_studio_database(db)
        initialize_local_context(db)



class HttpRequest:
    def __init__(self):
        self.path = "/"
        self.payload = None
        self.headers = {}
        self.command = "GET"
        self.response = None

    def send(self, method=None):
        prepare_local_identity()
        with TestClient(app, base_url="http://127.0.0.1:8765") as client:
            self.response = client.request(method or self.command, self.path,
                                           json=self.payload, headers=self.headers)
        return self.response
