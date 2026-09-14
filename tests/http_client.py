"""Small request fixture; every send traverses the real FastAPI TestClient."""
from fastapi.testclient import TestClient
from react_server import app


class HttpRequest:
    def __init__(self):
        self.path = "/"
        self.payload = None
        self.headers = {}
        self.command = "GET"
        self.response = None

    def send(self, method=None):
        with TestClient(app, base_url="http://127.0.0.1:8765") as client:
            self.response = client.request(method or self.command, self.path,
                                           json=self.payload, headers=self.headers)
        return self.response
