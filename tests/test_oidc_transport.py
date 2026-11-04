"""Real endpoint rejection and resource cleanup, independent of JWT fixtures."""
import socket
import http.client
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from cryptography.fernet import Fernet
from api_test.oidc_client import LoginError, Settings, Transport


class OidcTransportTest(unittest.TestCase):
    def settings(self, issuer, **kwargs):
        return Settings(issuer, 'client', 'https://studio.example.test',
                        Fernet.generate_key().decode(), auth_method='none', **kwargs)

    def test_redirect_size_and_non_object_responses_are_rejected(self):
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                seen.append(self.path)
                body = b'[]' if self.path == '/array' else b'{"value":"' + b'x' * 200 + b'"}'
                self.send_response(302 if self.path == '/redirect' else 200)
                self.send_header('Location', '/target')
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            origin = f'http://127.0.0.1:{server.server_port}'
            transport = Transport(self.settings(origin, allow_http=True))
            for path, code in [('/redirect', 'oidc_endpoint_rejected'),
                               ('/array', 'invalid_oidc_response'),
                               ('/large', 'oidc_response_too_large')]:
                with self.subTest(path=path), self.assertRaises(LoginError) as result:
                    transport.json(origin + path, limit=64)
                self.assertEqual(result.exception.code, code)
            self.assertNotIn('/target', seen)
        finally:
            server.shutdown(); server.server_close(); worker.join(2)

    def test_private_address_needs_explicit_origin_permission(self):
        settings = self.settings('https://127.0.0.1:443')
        with patch('api_test.oidc_client.socket.create_connection') as connect:
            with self.assertRaises(LoginError) as result:
                Transport(settings).json(settings.issuer)
            self.assertEqual(result.exception.code, 'oidc_address_not_allowed')
            connect.assert_not_called()
        with self.assertRaises(LoginError) as result:
            Transport(settings).json('https://other.example.test/token')
        self.assertEqual(result.exception.code, 'oidc_endpoint_not_allowed')

    def test_closed_pinned_connection_cannot_reconnect(self):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0)); listener.listen()
        origin = f'http://127.0.0.1:{listener.getsockname()[1]}'
        original_request = http.client.HTTPConnection.request
        def close_before_request(connection, *args, **kwargs):
            connection.close()
            return original_request(connection, *args, **kwargs)
        try:
            with patch('api_test.oidc_client.socket.create_connection', wraps=socket.create_connection) as connect:
                with patch.object(http.client.HTTPConnection, 'request', close_before_request):
                    with self.assertRaises(LoginError) as result:
                        Transport(self.settings(origin, allow_http=True)).json(origin)
                self.assertEqual(result.exception.code, 'oidc_endpoint_unavailable')
                self.assertEqual(connect.call_count, 1)
        finally: listener.close()

    def test_invalid_ca_file_closes_connected_socket(self):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0)); listener.listen(); listener.settimeout(3)
        origin = f'https://127.0.0.1:{listener.getsockname()[1]}'
        settings = self.settings(origin, private_origins=(origin,), ca_file='/nonexistent/studio-test-ca.pem')
        try:
            with self.assertRaises(LoginError): Transport(settings).json(origin)
            peer, _ = listener.accept()
            with peer:
                peer.settimeout(2)
                self.assertEqual(peer.recv(1), b'')
        finally: listener.close()

    def test_stalled_tls_handshake_is_bounded_and_closes_peer(self):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0)); listener.listen(); listener.settimeout(12)
        origin = f'https://127.0.0.1:{listener.getsockname()[1]}'
        closed = threading.Event()
        errors = []
        def stall():
            try:
                peer, _ = listener.accept()
                with peer:
                    peer.settimeout(11)
                    while peer.recv(65536): pass
                    closed.set()
            except OSError as exc: errors.append(exc)
        worker = threading.Thread(target=stall, daemon=True); worker.start()
        started = time.monotonic()
        try:
            with self.assertRaises(LoginError) as result:
                Transport(self.settings(origin, private_origins=(origin,))).json(origin)
            self.assertEqual(result.exception.code, 'oidc_endpoint_unavailable')
            self.assertLess(time.monotonic() - started, 10)
            self.assertTrue(closed.wait(2), errors)
        finally:
            listener.close(); worker.join(2)
