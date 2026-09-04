from __future__ import annotations

import unittest

from api_test.authorization import AuthorizationError, apply_authorization


class AuthorizationTest(unittest.TestCase):
    def test_adds_api_key_to_header_or_query(self) -> None:
        header = apply_authorization("https://api.example.test/users", "GET", {}, {"type": "API Key", "key": "X-API-Key", "value": "secret", "addTo": "Header"})
        query = apply_authorization("https://api.example.test/users", "GET", {}, {"type": "API Key", "key": "api_key", "value": "secret", "addTo": "Query Params"})
        self.assertEqual(header.headers["X-API-Key"], "secret")
        self.assertEqual(query.url, "https://api.example.test/users?api_key=secret")

    def test_adds_standard_header_token_types(self) -> None:
        for auth_type in ("Bearer Token", "OAuth 2.0", "JWT Bearer", "ASAP (Atlassian)"):
            request = apply_authorization("https://api.example.test/users", "GET", {}, {"type": auth_type, "token": "token"})
            self.assertEqual(request.headers["Authorization"], "Bearer token")

    def test_adds_basic_oauth_hawk_aws_and_edgegrid_signatures(self) -> None:
        basic = apply_authorization("https://api.example.test/users", "GET", {}, {"type": "Basic Auth", "username": "ada", "password": "pass"})
        oauth = apply_authorization("https://api.example.test/users", "GET", {}, {"type": "OAuth 1.0", "consumerKey": "consumer", "consumerSecret": "secret", "signatureMethod": "HMAC-SHA256", "nonce": "n", "timestamp": "1"})
        hawk = apply_authorization("https://api.example.test/users", "GET", {}, {"type": "Hawk Authentication", "id": "id", "key": "secret", "algorithm": "sha256", "nonce": "n", "timestamp": "1"})
        aws = apply_authorization("https://api.example.test/users", "GET", {}, {"type": "AWS Signature", "accessKey": "access", "secretKey": "secret", "region": "ap-northeast-2", "service": "execute-api"})
        edgegrid = apply_authorization("https://api.example.test/users", "GET", {}, {"type": "Akamai EdgeGrid", "accessToken": "access", "clientToken": "client", "clientSecret": "secret"})
        self.assertEqual(basic.headers["Authorization"], "Basic YWRhOnBhc3M=")
        self.assertTrue(oauth.headers["Authorization"].startswith("OAuth "))
        self.assertTrue(hawk.headers["Authorization"].startswith("Hawk "))
        self.assertTrue(aws.headers["Authorization"].startswith("AWS4-HMAC-SHA256 "))
        self.assertTrue(edgegrid.headers["Authorization"].startswith("EG1-HMAC-SHA256 "))

    def test_digest_and_ntlm_are_deferred_to_http_handshakes(self) -> None:
        digest = apply_authorization("https://api.example.test/users", "GET", {}, {"type": "Digest Auth", "username": "ada", "password": "pass"})
        ntlm = apply_authorization("https://api.example.test/users", "GET", {}, {"type": "NTLM Authentication", "username": "ada", "password": "pass"})
        self.assertEqual(digest.headers, {})
        self.assertEqual(ntlm.headers, {})
        with self.assertRaises(AuthorizationError):
            apply_authorization("https://api.example.test/users", "GET", {}, {"type": "Digest Auth"})
