import json
from io import BytesIO
from unittest.mock import patch

from django.test import SimpleTestCase

from ai_service.ieee_checker.services.crossref_client import verify_doi


class _FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class VerifyDoiTests(SimpleTestCase):
    def test_verified_doi_returns_true_with_title(self):
        payload = {"status": "ok", "message": {"title": ["A Verified Paper Title"]}}
        with patch("urllib.request.urlopen", return_value=_FakeResponse(payload)):
            verified, message = verify_doi("10.1109/EXAMPLE.2020.123")
        self.assertTrue(verified)
        self.assertIn("A Verified Paper Title", message)

    def test_non_ok_status_returns_false(self):
        payload = {"status": "error"}
        with patch("urllib.request.urlopen", return_value=_FakeResponse(payload)):
            verified, message = verify_doi("10.1109/NOTFOUND.2020.123")
        self.assertFalse(verified)
        self.assertIn("لم يُوجد", message)

    def test_network_failure_returns_false_with_error_message(self):
        with patch("urllib.request.urlopen", side_effect=OSError("network unreachable")):
            verified, message = verify_doi("10.1109/EXAMPLE.2020.123")
        self.assertFalse(verified)
        self.assertIn("تعذّر التحقق", message)
