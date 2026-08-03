import subprocess
from unittest.mock import patch

from django.test import SimpleTestCase

from ai_service.utils import nltk_setup


class EnsureNltkPunktTests(SimpleTestCase):
    def setUp(self):
        # _download_unavailable is a module-level cache shared across the whole test process;
        # snapshot and restore it so tests don't leak state into each other or into the real
        # first-caller (this project's own tests already trigger this cache in this sandboxed
        # environment, where punkt genuinely cannot be downloaded).
        self._saved_unavailable = set(nltk_setup._download_unavailable)

    def tearDown(self):
        nltk_setup._download_unavailable.clear()
        nltk_setup._download_unavailable.update(self._saved_unavailable)

    def test_resource_already_present_returns_true_without_downloading(self):
        nltk_setup._download_unavailable.clear()
        with patch("nltk.data.find"), patch("subprocess.run") as mock_run:
            result = nltk_setup.ensure_nltk_punkt()
        self.assertTrue(result)
        mock_run.assert_not_called()

    def test_missing_resource_attempts_download_and_succeeds(self):
        nltk_setup._download_unavailable.clear()
        with patch("nltk.data.find", side_effect=LookupError), patch("subprocess.run") as mock_run:
            result = nltk_setup.ensure_nltk_punkt()
        self.assertTrue(result)
        self.assertEqual(mock_run.call_count, 2)

    def test_download_timeout_marks_resource_unavailable_and_returns_false(self):
        nltk_setup._download_unavailable.clear()
        with patch("nltk.data.find", side_effect=LookupError), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=8)):
            result = nltk_setup.ensure_nltk_punkt()
        self.assertFalse(result)
        self.assertIn("punkt", nltk_setup._download_unavailable)

    def test_previously_unavailable_resource_short_circuits_without_retrying(self):
        nltk_setup._download_unavailable.clear()
        nltk_setup._download_unavailable.add("punkt")
        with patch("nltk.data.find", side_effect=LookupError), patch("subprocess.run") as mock_run:
            result = nltk_setup.ensure_nltk_punkt()
        self.assertFalse(result)
        mock_run.assert_not_called()
