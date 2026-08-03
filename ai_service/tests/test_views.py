from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ai_service.models import ClaimEvidenceGraphReport, IEEECheckReport
from research.models import ResearchPaper

User = get_user_model()


def make_user(email, role="author", **kwargs):
    return User.objects.create_user(
        email=email, full_name="Test User", password="pass1234", specialization="law", role=role, **kwargs
    )


class KeywordSuggestionViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("ai_service:keyword-suggest")
        self.user = make_user("kw@example.com")

    def test_unauthenticated_rejected(self):
        response = self.client.post(self.url, {"text": "some text"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_text_and_paper_id_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_success_with_text(self):
        self.client.force_authenticate(user=self.user)
        with patch("ai_service.utils.ai_keywordExtractor.AIKeywordExtractor") as mock_cls:
            mock_cls.return_value.extract_pure_keywords.return_value = ["ai", "keywords"]
            response = self.client.post(self.url, {"text": "some long enough text"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["keywords"], ["ai", "keywords"])

    def test_extraction_exception_is_non_blocking(self):
        self.client.force_authenticate(user=self.user)
        with patch("ai_service.utils.ai_keywordExtractor.AIKeywordExtractor") as mock_cls:
            mock_cls.return_value.extract_pure_keywords.side_effect = RuntimeError("boom")
            response = self.client.post(self.url, {"text": "some long enough text"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["keywords"], [])
        self.assertIn("note", response.data)

    def test_paper_id_used_when_text_missing(self):
        self.client.force_authenticate(user=self.user)
        paper = ResearchPaper.objects.create(
            title="My Paper", abstract="My abstract", author=self.user, specialization="law",
        )
        with patch("ai_service.utils.ai_keywordExtractor.AIKeywordExtractor") as mock_cls:
            mock_cls.return_value.extract_pure_keywords.return_value = ["kw"]
            response = self.client.post(self.url, {"paper_id": paper.id}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_cls.return_value.extract_pure_keywords.assert_called_once()
        called_text = mock_cls.return_value.extract_pure_keywords.call_args[0][0]
        self.assertIn("My Paper", called_text)
        self.assertIn("My abstract", called_text)

    def test_paper_id_not_found_returns_404(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, {"paper_id": 9999}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class IEEECheckViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("ai_service:ieee-check")
        self.editor = make_user("editor@example.com", role="editor")
        self.assistant_editor = make_user("assistant@example.com", role="assistant_editor")
        self.author = make_user("author@example.com", role="author")

    def _pdf_file(self, name="paper.pdf", content=b"%PDF-1.4 fake content"):
        return SimpleUploadedFile(name, content, content_type="application/pdf")

    def test_unauthenticated_rejected(self):
        response = self.client.post(self.url, {"document_file": self._pdf_file()}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wrong_role_rejected(self):
        self.client.force_authenticate(user=self.author)
        response = self.client.post(self.url, {"document_file": self._pdf_file()}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_file_returns_400(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.post(self.url, {}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wrong_extension_returns_400(self):
        self.client.force_authenticate(user=self.editor)
        bad_file = SimpleUploadedFile("paper.txt", b"content", content_type="text/plain")
        response = self.client.post(self.url, {"document_file": bad_file}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_oversized_file_returns_400(self):
        self.client.force_authenticate(user=self.editor)
        big_content = b"a" * (10 * 1024 * 1024 + 1)
        big_file = SimpleUploadedFile("paper.pdf", big_content, content_type="application/pdf")
        response = self.client.post(self.url, {"document_file": big_file}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_success_dispatches_task_and_returns_report(self):
        self.client.force_authenticate(user=self.editor)
        with patch("ai_service.views.analyze_ieee_check_task.delay") as mock_delay:
            response = self.client.post(
                self.url, {"document_file": self._pdf_file(), "verify_crossref": "false"}, format="multipart"
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_delay.assert_called_once()
        self.assertTrue(IEEECheckReport.objects.filter(id=response.data["id"]).exists())

    def test_assistant_editor_allowed(self):
        self.client.force_authenticate(user=self.assistant_editor)
        with patch("ai_service.views.analyze_ieee_check_task.delay"):
            response = self.client.post(self.url, {"document_file": self._pdf_file()}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_task_dispatch_failure_marks_report_error(self):
        self.client.force_authenticate(user=self.editor)
        with patch("ai_service.views.analyze_ieee_check_task.delay", side_effect=RuntimeError("celery down")):
            response = self.client.post(self.url, {"document_file": self._pdf_file()}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], IEEECheckReport.Status.ERROR)

    def test_accepts_pdf_file_field_alias(self):
        self.client.force_authenticate(user=self.editor)
        with patch("ai_service.views.analyze_ieee_check_task.delay"):
            response = self.client.post(self.url, {"pdf_file": self._pdf_file()}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class IEEEReportListViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("ai_service:ieee-report-list")
        self.editor = make_user("editor2@example.com", role="editor")
        self.author = make_user("author2@example.com", role="author")
        self.report_mine = IEEECheckReport.objects.create(
            original_filename="a.pdf", status=IEEECheckReport.Status.PASS, requested_by=self.editor,
        )
        self.report_other = IEEECheckReport.objects.create(
            original_filename="b.pdf", status=IEEECheckReport.Status.FAIL,
        )

    def test_unauthenticated_rejected(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wrong_role_rejected(self):
        self.client.force_authenticate(user=self.author)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_lists_all_reports_by_default(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_filters_by_status(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.get(self.url, {"status": "pass"})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.report_mine.id)

    def test_filters_by_mine(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.get(self.url, {"mine": "true"})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.report_mine.id)


class IEEEReportDetailViewTests(APITestCase):
    def setUp(self):
        self.editor = make_user("editor3@example.com", role="editor")
        self.report = IEEECheckReport.objects.create(original_filename="a.pdf")
        self.url = reverse("ai_service:ieee-report-detail", kwargs={"pk": self.report.id})

    def test_unauthenticated_rejected(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_not_found_returns_404(self):
        self.client.force_authenticate(user=self.editor)
        url = reverse("ai_service:ieee-report-detail", kwargs={"pk": 9999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_success(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.report.id)

    def test_delete_not_found_returns_404(self):
        self.client.force_authenticate(user=self.editor)
        url = reverse("ai_service:ieee-report-detail", kwargs={"pk": 9999})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_success(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(IEEECheckReport.objects.filter(id=self.report.id).exists())


class ClaimEvidenceGraphAnalyzeViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("ai_service:claim-evidence-analyze")
        self.editor = make_user("editor4@example.com", role="editor")
        self.author = make_user("author4@example.com", role="author")

    def _doc_file(self, name="paper.pdf"):
        return SimpleUploadedFile(name, b"fake content", content_type="application/pdf")

    def test_unauthenticated_rejected(self):
        response = self.client.post(self.url, {"document_file": self._doc_file()}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wrong_role_rejected(self):
        self.client.force_authenticate(user=self.author)
        response = self.client.post(self.url, {"document_file": self._doc_file()}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_file_returns_400(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.post(self.url, {}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wrong_extension_returns_400(self):
        self.client.force_authenticate(user=self.editor)
        bad_file = SimpleUploadedFile("paper.txt", b"content", content_type="text/plain")
        response = self.client.post(self.url, {"document_file": bad_file}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_oversized_file_returns_400(self):
        self.client.force_authenticate(user=self.editor)
        big_content = b"a" * (10 * 1024 * 1024 + 1)
        big_file = SimpleUploadedFile("paper.pdf", big_content, content_type="application/pdf")
        response = self.client.post(self.url, {"document_file": big_file}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_success_dispatches_task(self):
        self.client.force_authenticate(user=self.editor)
        with patch("ai_service.views.analyze_claim_evidence_graph_task.delay") as mock_delay:
            response = self.client.post(self.url, {"document_file": self._doc_file()}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_delay.assert_called_once()

    def test_invalid_threshold_falls_back_to_default(self):
        self.client.force_authenticate(user=self.editor)
        with patch("ai_service.views.analyze_claim_evidence_graph_task.delay"):
            response = self.client.post(
                self.url,
                {"document_file": self._doc_file(), "similarity_threshold": "not-a-number"},
                format="multipart",
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        report = ClaimEvidenceGraphReport.objects.get(id=response.data["id"])
        self.assertEqual(report.similarity_threshold, 0.2)

    def test_threshold_out_of_range_is_clamped(self):
        self.client.force_authenticate(user=self.editor)
        with patch("ai_service.views.analyze_claim_evidence_graph_task.delay"):
            response = self.client.post(
                self.url,
                {"document_file": self._doc_file(), "similarity_threshold": "5"},
                format="multipart",
            )
        report = ClaimEvidenceGraphReport.objects.get(id=response.data["id"])
        self.assertEqual(report.similarity_threshold, 1.0)

    def test_invalid_top_claims_count_falls_back_to_default(self):
        self.client.force_authenticate(user=self.editor)
        with patch("ai_service.views.analyze_claim_evidence_graph_task.delay"):
            response = self.client.post(
                self.url,
                {"document_file": self._doc_file(), "top_claims_count": "not-an-int"},
                format="multipart",
            )
        report = ClaimEvidenceGraphReport.objects.get(id=response.data["id"])
        self.assertEqual(report.top_claims_count, 10)

    def test_top_claims_count_out_of_range_is_clamped(self):
        self.client.force_authenticate(user=self.editor)
        with patch("ai_service.views.analyze_claim_evidence_graph_task.delay"):
            response = self.client.post(
                self.url,
                {"document_file": self._doc_file(), "top_claims_count": "1000"},
                format="multipart",
            )
        report = ClaimEvidenceGraphReport.objects.get(id=response.data["id"])
        self.assertEqual(report.top_claims_count, 50)

    def test_task_dispatch_failure_marks_report_failed(self):
        self.client.force_authenticate(user=self.editor)
        with patch("ai_service.views.analyze_claim_evidence_graph_task.delay", side_effect=RuntimeError("down")):
            response = self.client.post(self.url, {"document_file": self._doc_file()}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], ClaimEvidenceGraphReport.Status.FAILED)


class ClaimEvidenceGraphReportListViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("ai_service:claim-evidence-report-list")
        self.editor = make_user("editor5@example.com", role="editor")
        self.author = make_user("author5@example.com", role="author")
        self.report_mine = ClaimEvidenceGraphReport.objects.create(
            original_filename="a.pdf", status=ClaimEvidenceGraphReport.Status.COMPLETED, requested_by=self.editor,
        )
        self.report_other = ClaimEvidenceGraphReport.objects.create(
            original_filename="b.pdf", status=ClaimEvidenceGraphReport.Status.FAILED,
        )

    def test_unauthenticated_rejected(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wrong_role_rejected(self):
        self.client.force_authenticate(user=self.author)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_lists_all_by_default(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.get(self.url)
        self.assertEqual(len(response.data), 2)

    def test_filters_by_status(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.get(self.url, {"status": "failed"})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.report_other.id)

    def test_filters_by_mine(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.get(self.url, {"mine": "true"})
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.report_mine.id)


class ClaimEvidenceGraphReportDetailViewTests(APITestCase):
    def setUp(self):
        self.owner = make_user("owner@example.com", role="editor")
        self.admin = make_user("admin@example.com", role="admin")
        self.other_editor = make_user("othereditor@example.com", role="editor")
        self.owned_report = ClaimEvidenceGraphReport.objects.create(
            original_filename="a.pdf", requested_by=self.owner,
        )
        self.orphan_report = ClaimEvidenceGraphReport.objects.create(original_filename="b.pdf")

    def test_unauthenticated_rejected(self):
        url = reverse("ai_service:claim-evidence-report-detail", kwargs={"pk": self.owned_report.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_not_found_returns_404(self):
        self.client.force_authenticate(user=self.owner)
        url = reverse("ai_service:claim-evidence-report-detail", kwargs={"pk": 9999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # NOTE (application bug, not fixed here per task instructions): ai_service/views.py's
    # ClaimEvidenceGraphReportDetailView._forbidden_if_not_owner (line ~262) compares
    # `request.user.id`, but accounts.User's primary key field is `user_id`, not `id` — the
    # custom user model never gets an implicit `id` AutoField. Any request that reaches the
    # `elif report.requested_by_id != request.user.id` branch (i.e. every request for a report
    # that HAS an owner, including the owner's own request and an admin's request) raises an
    # uncaught AttributeError instead of returning 200/403. Only the "orphan report" branch
    # (requested_by is None) is unaffected, since it never touches `.id`. The tests below pin
    # down this actual (buggy) behavior rather than the intended one.
    def test_owner_viewing_own_report_currently_crashes_due_to_user_id_bug(self):
        self.client.force_authenticate(user=self.owner)
        url = reverse("ai_service:claim-evidence-report-detail", kwargs={"pk": self.owned_report.id})
        with self.assertRaises(AttributeError):
            self.client.get(url)

    def test_non_owner_viewing_report_currently_crashes_due_to_user_id_bug(self):
        self.client.force_authenticate(user=self.other_editor)
        url = reverse("ai_service:claim-evidence-report-detail", kwargs={"pk": self.owned_report.id})
        with self.assertRaises(AttributeError):
            self.client.get(url)

    def test_admin_viewing_owned_report_currently_crashes_due_to_user_id_bug(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse("ai_service:claim-evidence-report-detail", kwargs={"pk": self.owned_report.id})
        with self.assertRaises(AttributeError):
            self.client.get(url)

    def test_orphan_report_only_visible_to_admin(self):
        self.client.force_authenticate(user=self.other_editor)
        url = reverse("ai_service:claim-evidence-report-detail", kwargs={"pk": self.orphan_report.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.admin)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_owner_deleting_own_report_currently_crashes_due_to_user_id_bug(self):
        self.client.force_authenticate(user=self.owner)
        url = reverse("ai_service:claim-evidence-report-detail", kwargs={"pk": self.owned_report.id})
        with self.assertRaises(AttributeError):
            self.client.delete(url)
        self.assertTrue(ClaimEvidenceGraphReport.objects.filter(id=self.owned_report.id).exists())

    def test_delete_not_found_returns_404(self):
        self.client.force_authenticate(user=self.owner)
        url = reverse("ai_service:claim-evidence-report-detail", kwargs={"pk": 9999})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
