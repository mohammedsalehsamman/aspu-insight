import shutil
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from committees.models import Committee, CommitteeMember
from configuration.models import JournalConfiguration
from research.models import PlagiarismReport, ResearchPaper
from research.service import ResearchPaperService

User = get_user_model()


def make_user(email, role='author', **kwargs):
    return User.objects.create(email=email, full_name=email, role=role, specialization='law', **kwargs)


class ListCreatePapersTests(APITestCase):
    def setUp(self):
        self.url = reverse('paper-list-create')
        self.author = make_user('author@example.com')
        self.published = ResearchPaper.objects.create(
            title='Published', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.PUBLISHED,
        )
        self.private = ResearchPaper.objects.create(
            title='Private', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.PENDING,
        )

    def test_anonymous_get_sees_only_published(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [p['title'] for p in response.data]
        self.assertIn('Published', titles)
        self.assertNotIn('Private', titles)

    def test_authenticated_author_sees_own_private_paper_too(self):
        self.client.force_authenticate(user=self.author)
        response = self.client.get(self.url)
        titles = [p['title'] for p in response.data]
        self.assertIn('Private', titles)

    @patch('research.service.compute_paper_embedding_task')
    @patch('research.service.check_paper_plagiarism_task')
    def test_authenticated_user_can_create_paper(self, mock_plagiarism_task, mock_embedding_task):
        self.client.force_authenticate(user=self.author)
        response = self.client.post(self.url, {
            'title': 'New Paper', 'abstract': 'abstract text', 'specialization': 'law',
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = ResearchPaper.objects.get(title='New Paper')
        self.assertEqual(created.author, self.author)

    def test_anonymous_cannot_create_paper(self):
        response = self.client.post(self.url, {
            'title': 'New Paper', 'abstract': 'abstract text', 'specialization': 'law',
        }, format='multipart')
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_create_paper_missing_required_fields_returns_400(self):
        self.client.force_authenticate(user=self.author)
        response = self.client.post(self.url, {'title': 'No abstract'}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class SmartSearchViewTests(APITestCase):
    def setUp(self):
        self.url = reverse('paper-smart-search')
        self.author = make_user('author@example.com')
        self.paper = ResearchPaper.objects.create(
            title='Matched', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.PUBLISHED,
        )

    @patch('ai_service.services.research_recommendation.AIPaperSearchService.semantic_search')
    def test_returns_ranked_results_from_ai_service(self, mock_search):
        mock_search.return_value = [self.paper]
        response = self.client.get(self.url, {'q': 'anything'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], 'Matched')
        mock_search.assert_called_once()

    @patch('ai_service.services.research_recommendation.AIPaperSearchService.semantic_search')
    def test_empty_results_from_ai_service(self, mock_search):
        mock_search.return_value = []
        response = self.client.get(self.url, {'q': 'nothing'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])


class SimilarPapersViewTests(APITestCase):
    def setUp(self):
        self.author = make_user('author@example.com')
        self.paper = ResearchPaper.objects.create(
            title='Base', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.PUBLISHED,
        )
        self.candidate = ResearchPaper.objects.create(
            title='Candidate', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.PUBLISHED,
        )

    def test_returns_404_for_missing_paper(self):
        url = reverse('paper-recommendations', kwargs={'paper_id': 9999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch('ai_service.services.research_recommendation.AIPaperSearchService.recommend_similar_papers')
    def test_returns_recommended_papers(self, mock_recommend):
        mock_recommend.return_value = [self.candidate]
        url = reverse('paper-recommendations', kwargs={'paper_id': self.paper.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], 'Candidate')


class PaperDetailGetTests(APITestCase):
    def setUp(self):
        self.author = make_user('author@example.com')
        self.stranger = make_user('stranger@example.com')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.SUBMITTED,
        )
        self.url = reverse('paper-detail', kwargs={'paper_id': self.paper.id})

    def test_404_for_missing_paper(self):
        url = reverse('paper-detail', kwargs={'paper_id': 9999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_403_when_not_authorized_to_view(self):
        self.client.force_authenticate(user=self.stranger)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_author_can_view_own_paper(self):
        self.client.force_authenticate(user=self.author)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class PaperDetailPutDeletePermissionTests(APITestCase):
    """Basic ownership-gate checks (not the field-level enforcement finding below)."""

    def setUp(self):
        self.author = make_user('author@example.com')
        self.stranger = make_user('stranger@example.com')
        self.staff = make_user('staff@example.com', is_staff=True)
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.SUBMITTED,
        )
        self.url = reverse('paper-detail', kwargs={'paper_id': self.paper.id})

    def test_put_404_for_missing_paper(self):
        url = reverse('paper-detail', kwargs={'paper_id': 9999})
        self.client.force_authenticate(user=self.author)
        response = self.client.put(url, {'title': 'x'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_put_403_for_non_author_non_staff(self):
        self.client.force_authenticate(user=self.stranger)
        response = self.client.put(self.url, {
            'title': 'hacked', 'abstract': 'a', 'specialization': 'law',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.title, 'Paper')

    def test_put_allowed_for_staff_non_owner(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.put(self.url, {
            'title': 'edited by staff', 'abstract': 'a', 'specialization': 'law',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.title, 'edited by staff')

    def test_delete_404_for_missing_paper(self):
        url = reverse('paper-detail', kwargs={'paper_id': 9999})
        self.client.force_authenticate(user=self.author)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_403_for_non_author_non_staff(self):
        self.client.force_authenticate(user=self.stranger)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(ResearchPaper.objects.filter(pk=self.paper.pk).exists())


class PutDeleteSerializerEnforcementFindingTests(APITestCase):
    """
    Investigates the specific concern raised by the project owner: does
    ResearchPaperDetailAPIView.put()/delete() enforce the same business rules
    that research/service.py declares (ResearchPaperService.can_update /
    can_delete), or only the bare author/staff ownership check?
    """

    def setUp(self):
        self.author = make_user('author@example.com')
        self.editor = make_user('editor@example.com', role='editor')
        self.paper = ResearchPaper.objects.create(
            title='Original Title', abstract='original abstract', author=self.author,
            specialization='law', status=ResearchPaper.Status.SUBMITTED,
            rejection_reason='', is_reviewed_by_assistant=False,
        )
        self.url = reverse('paper-detail', kwargs={'paper_id': self.paper.id})

    def test_plain_author_can_set_status_to_published_via_put(self):
        """
        PROOF: a plain (non-staff) author PUTting to paper-detail can set
        status directly to PUBLISHED, completely bypassing the assistant
        review / editor review / committee pipeline that normally drives
        status transitions (and that also logs a ResearchHistory entry).
        """
        self.client.force_authenticate(user=self.author)
        response = self.client.put(self.url, {
            'title': 'Original Title',
            'abstract': 'original abstract',
            'specialization': 'law',
            'status': ResearchPaper.Status.PUBLISHED,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.PUBLISHED)

    def test_plain_author_can_set_is_reviewed_by_assistant_via_put(self):
        """
        PROOF: a plain author can flip is_reviewed_by_assistant to True
        themselves, even though this flag is meant to be set only by
        AssistantReviewService and gates editor/committee visibility
        (see research/service.py can_view and get_visible_papers).
        """
        self.client.force_authenticate(user=self.author)
        response = self.client.put(self.url, {
            'title': 'Original Title',
            'abstract': 'original abstract',
            'specialization': 'law',
            'is_reviewed_by_assistant': True,
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.paper.refresh_from_db()
        self.assertTrue(self.paper.is_reviewed_by_assistant)

    def test_plain_author_can_set_rejection_reason_via_put(self):
        self.client.force_authenticate(user=self.author)
        response = self.client.put(self.url, {
            'title': 'Original Title',
            'abstract': 'original abstract',
            'specialization': 'law',
            'rejection_reason': 'author-written fake rejection reason',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.rejection_reason, 'author-written fake rejection reason')

    def test_only_review_blindness_type_is_actually_protected(self):
        """review_blindness_type IS the one field DRF blocks (declared read_only),
        confirming the other sensitive fields are protected by nothing at all."""
        self.client.force_authenticate(user=self.author)
        response = self.client.put(self.url, {
            'title': 'Original Title',
            'abstract': 'original abstract',
            'specialization': 'law',
            'review_blindness_type': 'open_review',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.review_blindness_type, 'double_blind')  # unchanged

    def test_status_change_via_put_does_not_create_a_research_history_entry(self):
        """Contrast with the legitimate pipeline (assistantReview/editorReview),
        which always logs a ResearchHistory entry on status transitions."""
        from researchHistory.models import ResearchHistory

        self.client.force_authenticate(user=self.author)
        self.client.put(self.url, {
            'title': 'Original Title',
            'abstract': 'original abstract',
            'specialization': 'law',
            'status': ResearchPaper.Status.PUBLISHED,
        }, format='json')

        self.assertEqual(ResearchHistory.objects.filter(paper=self.paper).count(), 0)

    def test_delete_view_bypasses_can_delete_business_rule_gate(self):
        """
        PROOF: research/service.py defines ResearchPaperService.can_delete()
        (== can_update()), which forbids an author from deleting/updating a
        paper once a Committee exists and the paper's status has moved past
        REVISION_REQUIRED/REJECTED (e.g. COMMITTEE_REVIEW, PUBLISHED). The
        view's delete() never calls this service method — it only checks
        author/staff ownership — so the author can delete the paper anyway.
        """
        Committee.objects.create(paper=self.paper, editor=self.editor)
        self.paper.status = ResearchPaper.Status.COMMITTEE_REVIEW
        self.paper.save()

        # Confirm the service-layer rule says this should NOT be allowed.
        self.assertFalse(ResearchPaperService.can_delete(self.author, self.paper))

        self.client.force_authenticate(user=self.author)
        response = self.client.delete(self.url)

        # But the view allows it anyway.
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ResearchPaper.objects.filter(pk=self.paper.pk).exists())

    def test_delete_view_bypasses_can_delete_gate_for_published_paper(self):
        Committee.objects.create(paper=self.paper, editor=self.editor)
        self.paper.status = ResearchPaper.Status.PUBLISHED
        self.paper.save()

        self.assertFalse(ResearchPaperService.can_delete(self.author, self.paper))

        self.client.force_authenticate(user=self.author)
        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ResearchPaper.objects.filter(pk=self.paper.pk).exists())

    def test_put_view_also_bypasses_can_update_business_rule_gate(self):
        Committee.objects.create(paper=self.paper, editor=self.editor)
        self.paper.status = ResearchPaper.Status.COMMITTEE_REVIEW
        self.paper.save()

        self.assertFalse(ResearchPaperService.can_update(self.author, self.paper))

        self.client.force_authenticate(user=self.author)
        response = self.client.put(self.url, {
            'title': 'edited despite committee review',
            'abstract': 'original abstract',
            'specialization': 'law',
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.title, 'edited despite committee review')


class DownloadPaperViewTests(APITestCase):
    """
    Uses a throwaway temp MEDIA_ROOT (instead of the project's real media/
    folder) so uploaded test PDFs never land in the repo, and skips manual
    file deletion in tearDown: FileResponse keeps the file handle open past
    the test client's response cycle, and deleting it immediately trips a
    Windows file-lock (PermissionError) since the OS won't unlink an open
    file. Cleanup is handled by removing the whole temp dir once, ignoring
    any still-locked handles.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import tempfile
        cls._media_dir = tempfile.mkdtemp(prefix='research_download_tests_')
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_dir)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_dir, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.author = make_user('author@example.com')
        self.stranger = make_user('stranger@example.com')
        self.staff = make_user('staff@example.com', is_staff=True)
        self.pdf_content = SimpleUploadedFile('paper.pdf', b'%PDF-1.4 fake pdf content', content_type='application/pdf')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='a', author=self.author, specialization='law',
            status=ResearchPaper.Status.PUBLISHED, pdf_file=self.pdf_content,
        )
        self.url = reverse('paper-download', kwargs={'paper_id': self.paper.id})

    def test_404_for_missing_paper(self):
        url = reverse('paper-download', kwargs={'paper_id': 9999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_404_when_paper_has_no_pdf(self):
        paper = ResearchPaper.objects.create(
            title='No PDF', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.PUBLISHED,
        )
        url = reverse('paper-download', kwargs={'paper_id': paper.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_can_always_download(self):
        self.client.force_authenticate(user=self.author)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_staff_can_always_download(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_full_open_mode_allows_anyone(self):
        JournalConfiguration.objects.create(system_mode='full_open')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_no_config_defaults_to_full_open(self):
        self.assertFalse(JournalConfiguration.objects.exists())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_hybrid_mode_denies_non_open_access_paper_for_stranger(self):
        JournalConfiguration.objects.create(system_mode='hybrid')
        self.client.force_authenticate(user=self.stranger)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_hybrid_mode_allows_paid_open_access_paper_for_stranger(self):
        JournalConfiguration.objects.create(system_mode='hybrid')
        self.paper.is_paid_open_access = True
        self.paper.save()
        self.client.force_authenticate(user=self.stranger)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_full_closed_mode_denies_stranger(self):
        JournalConfiguration.objects.create(system_mode='full_closed')
        self.client.force_authenticate(user=self.stranger)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class PlagiarismReportViewTests(APITestCase):
    def setUp(self):
        self.author = make_user('author@example.com')
        self.stranger = make_user('stranger@example.com')
        self.assistant = make_user('assistant@example.com', role='assistant_editor')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.SUBMITTED,
        )
        self.url = reverse('paper-plagiarism-report', kwargs={'paper_id': self.paper.id})

    def test_unauthenticated_denied(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unrelated_user_without_view_access_denied(self):
        self.client.force_authenticate(user=self.stranger)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_author_with_existing_report_sees_it(self):
        PlagiarismReport.objects.create(paper=self.paper, total_similarity_score=10.0)
        self.client.force_authenticate(user=self.author)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_similarity_score'], 10.0)

    def test_assistant_can_view_report_even_without_being_author(self):
        PlagiarismReport.objects.create(paper=self.paper, total_similarity_score=5.0)
        self.client.force_authenticate(user=self.assistant)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('ai_service.tasks.check_paper_plagiarism_task')
    def test_missing_report_triggers_check_task_and_returns_pending_if_still_missing(self, mock_task):
        mock_task.side_effect = lambda paper_id: None  # does not create a report
        self.client.force_authenticate(user=self.author)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['status'], 'pending')
        mock_task.assert_called_once_with(self.paper.id)

    @patch('ai_service.tasks.check_paper_plagiarism_task')
    def test_missing_report_returns_report_once_task_creates_it(self, mock_task):
        def fake_task(paper_id):
            PlagiarismReport.objects.create(paper_id=paper_id, total_similarity_score=77.0)
        mock_task.side_effect = fake_task

        self.client.force_authenticate(user=self.author)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_similarity_score'], 77.0)


class AuthorDashboardViewTests(APITestCase):
    def setUp(self):
        self.author = make_user('author@example.com')
        self.other_author = make_user('other@example.com')
        self.own_paper = ResearchPaper.objects.create(
            title='Mine', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.PENDING,
        )
        self.other_paper = ResearchPaper.objects.create(
            title='Not mine', abstract='a', author=self.other_author,
            specialization='law', status=ResearchPaper.Status.PUBLISHED,
        )
        self.url = reverse('author-dashboard')

    def test_unauthenticated_denied(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_returns_only_own_papers(self):
        self.client.force_authenticate(user=self.author)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [p['title'] for p in response.data]
        self.assertEqual(titles, ['Mine'])
