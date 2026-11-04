"""Bounded local fake-provider transport and OAuth client authentication syntax."""
import base64
import json
import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import parse_qs

from api_test.oauth_transport import OAuthTransportError, post_token_form, validate_endpoint


class _Provider(BaseHTTPRequestHandler):
    captured = None

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode()
        _Provider.captured = {"path": self.path, "form": parse_qs(body), "authorization": self.headers.get("Authorization")}
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/token")
            self.end_headers()
            return
        if self.path == "/large":
            content = b"x" * (64 * 1024 + 1)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        if self.path == "/error":
            content = b'{"error_description":"provider-private-secret"}'
            self.send_response(400)
        elif self.path == "/slow":
            content = b'{"access_token":"slow","token_type":"Bearer"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            for part in content:
                try:
                    self.wfile.write(bytes([part]))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
                time.sleep(.05)
            return
        else:
            content = json.dumps({"access_token": "synthetic", "token_type": "Bearer", "expires_in": 60}).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *_):
        pass


class OAuthTransportTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"LOCAL_SERVER": "true"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Provider)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def test_basic_client_credentials_percent_encode_both_halves(self):
        response = post_token_form(self.base + "/token", {"grant_type": "client_credentials", "scope": "read write"},
                                   client_id="a:b+é", client_secret="s: +%", method="basic")
        self.assertEqual(response["access_token"], "synthetic")
        encoded = base64.b64decode(_Provider.captured["authorization"].removeprefix("Basic ")).decode("ascii")
        self.assertEqual(encoded, "a%3Ab%2B%C3%A9:s%3A+%2B%25")
        self.assertNotIn("client_secret", _Provider.captured["form"])
        self.assertNotIn("client_id", _Provider.captured["form"])

    def test_public_and_post_methods_keep_credentials_in_form_only(self):
        post_token_form(self.base + "/token", {"grant_type": "authorization_code"}, client_id="id", client_secret="secret", method="post")
        self.assertEqual(_Provider.captured["form"]["client_secret"], ["secret"])
        self.assertIsNone(_Provider.captured["authorization"])
        post_token_form(self.base + "/token", {"grant_type": "authorization_code"}, client_id="public", client_secret=None, method="none")
        self.assertEqual(_Provider.captured["form"]["client_id"], ["public"])
        self.assertNotIn("client_secret", _Provider.captured["form"])

    def test_redirect_size_provider_error_and_private_endpoint_are_sanitized(self):
        for path in ("/redirect", "/large", "/error"):
            with self.subTest(path=path), self.assertRaises(OAuthTransportError) as error:
                post_token_form(self.base + path, {"grant_type": "client_credentials"}, client_id="id", client_secret="secret", method="basic")
            self.assertNotIn("provider-private-secret", str(error.exception))
        with self.assertRaises(OAuthTransportError):
            validate_endpoint("http://169.254.169.254/token")
        with self.assertRaises(OAuthTransportError):
            validate_endpoint("https://example.test/\nother")
        with patch.dict(os.environ, {"LOCAL_SERVER": "false"}):
            with self.assertRaises(OAuthTransportError):
                validate_endpoint(self.base + "/token")

    def test_slow_drip_has_total_exchange_deadline(self):
        started = time.monotonic()
        with patch("api_test.oauth_transport.TIMEOUT_SECONDS", .25):
            with self.assertRaises(OAuthTransportError):
                post_token_form(self.base + "/slow", {"grant_type": "client_credentials"},
                                client_id="id", client_secret="secret", method="basic")
        self.assertLess(time.monotonic() - started, 2)

if __name__ == "__main__":
    unittest.main()
