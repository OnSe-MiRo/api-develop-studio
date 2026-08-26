from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


KEY_FILE_ENV = "ENCRYPTION_KEY_FILE"
INITIAL_KEY_ENV = "ENCRYPTION_INITIAL_KEY"
DEFAULT_KEY_FILE = "/var/lib/api-test-encryption/key"


def load_or_create_fernet(key_file: Path, initial_key: bytes | None = None) -> tuple[Fernet, bool]:
    key_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        key = key_file.read_bytes().strip()
    except FileNotFoundError:
        key = initial_key or Fernet.generate_key()
        fernet = Fernet(key)
        try:
            descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return load_or_create_fernet(key_file, initial_key)
        with os.fdopen(descriptor, "wb") as output:
            output.write(key + b"\n")
        return fernet, True
    return Fernet(key), False


class EncryptionHandler(BaseHTTPRequestHandler):
    fernet: Fernet

    def log_message(self, format: str, *args: object) -> None:
        return

    def send_json(self, status: int, payload: dict[str, str]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, {"status": "ok"})
            return
        self.send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.path not in {"/v1/encrypt", "/v1/decrypt"}:
            self.send_json(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError
            if self.path == "/v1/encrypt":
                value = payload.get("value")
                if not isinstance(value, str) or not value:
                    raise ValueError
                self.send_json(200, {"token": self.fernet.encrypt(value.encode("utf-8")).decode("ascii")})
                return
            token = payload.get("token")
            if not isinstance(token, str) or not token:
                raise ValueError
            self.send_json(200, {"value": self.fernet.decrypt(token.encode("ascii")).decode("utf-8")})
        except (InvalidToken, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            self.send_json(400, {"error": "Invalid encryption request"})


def main() -> None:
    key_file = Path(os.environ.get(KEY_FILE_ENV, DEFAULT_KEY_FILE))
    initial_key = os.environ.get(INITIAL_KEY_ENV, "").strip().encode("ascii") or None
    fernet, created = load_or_create_fernet(key_file, initial_key)
    EncryptionHandler.fernet = fernet
    if created:
        print(
            "[encryption] A persistent key was created. To inspect it, run: "
            f"docker compose exec encryption cat {key_file}",
            flush=True,
        )
    server = ThreadingHTTPServer(("0.0.0.0", 8766), EncryptionHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
