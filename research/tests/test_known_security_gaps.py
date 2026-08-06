import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from configuration.models import JournalConfiguration
from research.models import ResearchPaper

User = get_user_model()


def make_user(email, role='author', **kwargs):
    return User.objects.create(email=email, full_name=email, role=role, specialization='law', **kwargs)


class DownloadIDORTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_dir = tempfile.mkdtemp(prefix='research_security_gap_tests_')
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_dir)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_dir, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.author = make_user('author@example.com')
        self.stranger = make_user('stranger@example.com')

    def _unreviewed_paper(self, status_value):
        pdf = SimpleUploadedFile('paper.pdf', b'%PDF-1.4 fake pdf content', content_type='application/pdf')
        return ResearchPaper.objects.create(
            title='Unreviewed', abstract='a', author=self.author,
            specialization='law', status=status_value, pdf_file=pdf,
        )

    def test_full_open_mode_still_blocks_download_of_pending_paper_for_anonymous(self):
        JournalConfiguration.objects.create(system_mode='full_open')
        paper = self._unreviewed_paper(ResearchPaper.Status.PENDING)
        url = reverse('paper-download', kwargs={'paper_id': paper.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_full_open_mode_still_blocks_download_of_rejected_paper_for_stranger(self):
        JournalConfiguration.objects.create(system_mode='full_open')
        paper = self._unreviewed_paper(ResearchPaper.Status.REJECTED)
        self.client.force_authenticate(user=self.stranger)
        url = reverse('paper-download', kwargs={'paper_id': paper.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_config_row_defaults_to_full_open_but_still_blocks_unreviewed_paper(self):
        self.assertFalse(JournalConfiguration.objects.exists())
        paper = self._unreviewed_paper(ResearchPaper.Status.SUBMITTED)
        url = reverse('paper-download', kwargs={'paper_id': paper.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CreatePaperExceptionLeakTests(APITestCase):
    def setUp(self):
        self.url = reverse('paper-list-create')
        self.author = make_user('author@example.com')

    @patch('research.service.ResearchPaperService.create_paper')
    def test_server_error_does_not_leak_raw_exception_text(self, mock_create):
        mock_create.side_effect = ValueError("internal detail: db path /home/user/secret, row 42")
        self.client.force_authenticate(user=self.author)
        response = self.client.post(self.url, {
            'title': 'Paper', 'abstract': 'abstract text', 'specialization': 'law',
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        body = str(response.data)
        self.assertNotIn('internal detail', body)
        self.assertNotIn('/home/user/secret', body)


class ReviewBlindnessTypeNotSettableTests(APITestCase):
    @patch('research.service.compute_paper_embedding_task')
    @patch('research.service.check_paper_plagiarism_task')
    def test_author_can_set_review_blindness_type_on_create(self, mock_plagiarism, mock_embedding):
        author = make_user('author@example.com')
        self.client.force_authenticate(user=author)
        response = self.client.post(reverse('paper-list-create'), {
            'title': 'Paper', 'abstract': 'abstract text', 'specialization': 'law',
            'review_blindness_type': 'open_review',
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        paper = ResearchPaper.objects.get(title='Paper')
        self.assertEqual(
            paper.review_blindness_type, 'open_review',
            "review_blindness_type stayed at the model default instead of honoring the "
            "value submitted at creation — it's declared read_only on the serializer and "
            "never set explicitly by ResearchPaperService.create_paper()."
        )
