import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

from api_test.encryption_service import load_or_create_fernet
from api_test.project_variables import decrypt_secret, encrypt_secret


class ServiceResponse:
    def __init__(self, payload: dict[str, str]) -> None:
        self.payload = payload

    def __enter__(self) -> "ServiceResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class EncryptionServiceTest(unittest.TestCase):
    def test_key_is_created_once_and_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            key_file = Path(directory) / "key"
            first, created = load_or_create_fernet(key_file)
            second, created_again = load_or_create_fernet(key_file)

            token = first.encrypt(b"secret")
            self.assertTrue(created)
            self.assertFalse(created_again)
            self.assertEqual(second.decrypt(token), b"secret")
            self.assertEqual(key_file.stat().st_mode & 0o777, 0o600)

    def test_initial_key_is_persisted_for_existing_projects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            key_file = Path(directory) / "key"
            key = Fernet.generate_key()
            fernet, created = load_or_create_fernet(key_file, key)

            self.assertTrue(created)
            self.assertEqual(key_file.read_bytes().strip(), key)
            self.assertEqual(fernet.decrypt(Fernet(key).encrypt(b"secret")), b"secret")

    def test_project_variables_use_the_encryption_service_when_configured(self) -> None:
        responses = [ServiceResponse({"token": "encrypted-value"}), ServiceResponse({"value": "private-value"})]
        with patch.dict(os.environ, {"API_TEST_ENCRYPTION_URL": "http://encryption:8766"}, clear=False), patch(
            "api_test.project_variables.urlopen", side_effect=responses
        ) as urlopen:
            self.assertEqual(encrypt_secret("private-value"), "encrypted-value")
            self.assertEqual(decrypt_secret("encrypted-value"), "private-value")

        encrypt_request = urlopen.call_args_list[0].args[0]
        decrypt_request = urlopen.call_args_list[1].args[0]
        self.assertEqual(encrypt_request.full_url, "http://encryption:8766/v1/encrypt")
        self.assertEqual(json.loads(encrypt_request.data), {"value": "private-value"})
        self.assertEqual(decrypt_request.full_url, "http://encryption:8766/v1/decrypt")
        self.assertEqual(json.loads(decrypt_request.data), {"token": "encrypted-value"})


if __name__ == "__main__":
    unittest.main()
