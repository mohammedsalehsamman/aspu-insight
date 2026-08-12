from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from editorReview.models import EditorReview
from research.models import ResearchPaper

User = get_user_model()


class EditorInitialReviewAPIViewTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create(
            email="author@example.com", full_name="Author", specialization="law", email_verified=True,
        )
        self.editor = User.objects.create(
            email="editor@example.com", full_name="Editor", role="editor", specialization="law",
            email_verified=True,
        )
        self.other_editor = User.objects.create(
            email="editor2@example.com", full_name="Editor Two", role="editor", specialization="law",
            email_verified=True,
        )
        self.reviewer = User.objects.create(
            email="reviewer@example.com", full_name="Reviewer", role="reviewer", specialization="law",
            email_verified=True,
        )
        self.paper = ResearchPaper.objects.create(
            title="Paper", abstract="abstract", author=self.author,
            specialization="law", status=ResearchPaper.Status.EDITOR_REVIEW,
        )
        self.url = reverse("editor-review-initial", kwargs={"paper_id": self.paper.id})

    def test_unauthenticated_cannot_access(self):
        response = self.client.post(self.url, {"decision": "SEND_TO_COMMITTEE", "notes": "n"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_editor_role_forbidden(self):
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.post(self.url, {"decision": "SEND_TO_COMMITTEE", "notes": "n"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_editor_can_submit_initial_review(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.post(self.url, {"decision": "SEND_TO_COMMITTEE", "notes": "looks fine"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.COMMITTEE_REVIEW)

    def test_invalid_decision_returns_400(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.post(self.url, {"decision": "ACCEPT", "notes": "n"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_paper_not_awaiting_review_returns_400(self):
        self.paper.status = ResearchPaper.Status.SUBMITTED
        self.paper.save()

        self.client.force_authenticate(user=self.editor)
        response = self.client.post(self.url, {"decision": "SEND_TO_COMMITTEE", "notes": "n"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_review_assigned_to_different_editor_returns_400(self):
        self.paper.assigned_editor = self.other_editor
        self.paper.save()

        self.client.force_authenticate(user=self.editor)
        response = self.client.post(self.url, {"decision": "SEND_TO_COMMITTEE", "notes": "n"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_lists_only_initial_stage_reviews(self):
        EditorReview.objects.create(
            paper=self.paper, editor=self.editor, stage=EditorReview.Stage.INITIAL,
            notes="n1", decision=EditorReview.Decision.SEND_TO_COMMITTEE,
        )
        EditorReview.objects.create(
            paper=self.paper, editor=self.editor, stage=EditorReview.Stage.FINAL,
            notes="n2", decision=EditorReview.Decision.ACCEPT,
        )

        self.client.force_authenticate(user=self.editor)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["stage"], EditorReview.Stage.INITIAL)


class EditorFinalReviewAPIViewTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create(
            email="author@example.com", full_name="Author", specialization="law", email_verified=True,
        )
        self.editor = User.objects.create(
            email="editor@example.com", full_name="Editor", role="editor", specialization="law",
            email_verified=True,
        )
        self.paper = ResearchPaper.objects.create(
            title="Paper", abstract="abstract", author=self.author,
            specialization="law", status=ResearchPaper.Status.COMMITTEE_REVIEW,
        )
        self.url = reverse("editor-review-final", kwargs={"paper_id": self.paper.id})

    def test_unauthenticated_cannot_access(self):
        response = self.client.post(self.url, {"decision": "ACCEPT", "notes": "n"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_editor_role_forbidden(self):
        author = self.author
        self.client.force_authenticate(user=author)
        response = self.client.post(self.url, {"decision": "ACCEPT", "notes": "n"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_accept_without_checklist_returns_400(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.post(self.url, {"decision": "ACCEPT", "notes": "n"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_accept_with_full_checklist_succeeds(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.post(self.url, {
            "decision": "ACCEPT",
            "notes": "great work",
            "language_review_passed": True,
            "citation_check_passed": True,
            "publisher_permission_obtained": True,
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.ACCEPTED)

    def test_revision_required_does_not_need_checklist(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.post(self.url, {"decision": "REVISION_REQUIRED", "notes": "please revise"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.REVISION_REQUIRED)

    def test_paper_not_awaiting_final_review_returns_400(self):
        self.paper.status = ResearchPaper.Status.EDITOR_REVIEW
        self.paper.save()

        self.client.force_authenticate(user=self.editor)
        response = self.client.post(self.url, {"decision": "REJECT", "notes": "n"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PublishPaperAPIViewTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create(
            email="author@example.com", full_name="Author", specialization="law", email_verified=True,
        )
        self.editor = User.objects.create(
            email="editor@example.com", full_name="Editor", role="editor", specialization="law",
            email_verified=True,
        )
        self.paper = ResearchPaper.objects.create(
            title="Paper", abstract="abstract", author=self.author,
            specialization="law", status=ResearchPaper.Status.ACCEPTED,
        )
        self.url = reverse("publish-paper", kwargs={"paper_id": self.paper.id})

    def test_unauthenticated_cannot_access(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_editor_role_forbidden(self):
        self.client.force_authenticate(user=self.author)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_editor_can_publish_accepted_paper(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], ResearchPaper.Status.PUBLISHED)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.PUBLISHED)

    def test_publish_non_accepted_paper_returns_400(self):
        self.paper.status = ResearchPaper.Status.COMMITTEE_REVIEW
        self.paper.save()

        self.client.force_authenticate(user=self.editor)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AssignAssistantEditorAPIViewTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create(
            email="author@example.com", full_name="Author", specialization="law", email_verified=True,
        )
        self.editor = User.objects.create(
            email="editor@example.com", full_name="Editor", role="editor", specialization="law",
            email_verified=True,
        )
        self.other_editor = User.objects.create(
            email="editor2@example.com", full_name="Editor Two", role="editor", specialization="law",
            email_verified=True,
        )
        self.assistant_editor = User.objects.create(
            email="assistant@example.com", full_name="Assistant", role="assistant_editor", specialization="law",
            email_verified=True,
        )
        self.reviewer = User.objects.create(
            email="reviewer@example.com", full_name="Reviewer", role="reviewer", specialization="law",
            email_verified=True,
        )
        self.paper = ResearchPaper.objects.create(
            title="Paper", abstract="abstract", author=self.author,
            specialization="law", status=ResearchPaper.Status.SUBMITTED,
        )
        self.url = reverse("assign-assistant-editor", kwargs={"paper_id": self.paper.id})

    def test_unauthenticated_cannot_access(self):
        response = self.client.patch(
            self.url, {"assistant_editor_id": self.assistant_editor.user_id}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_editor_role_forbidden(self):
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.patch(
            self.url, {"assistant_editor_id": self.assistant_editor.user_id}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_editor_can_assign_assistant_editor(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.patch(
            self.url, {"assistant_editor_id": self.assistant_editor.user_id}, format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["assigned_assistant_editor"]["user_id"], self.assistant_editor.user_id,
        )
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.assigned_assistant_editor, self.assistant_editor)

    def test_target_user_not_assistant_editor_returns_404(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.patch(
            self.url, {"assistant_editor_id": self.reviewer.user_id}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_assistant_editor_id_returns_400(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.patch(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_assign_for_paper_assigned_to_different_editor_returns_400(self):
        self.paper.assigned_editor = self.other_editor
        self.paper.save()

        self.client.force_authenticate(user=self.editor)
        response = self.client.patch(
            self.url, {"assistant_editor_id": self.assistant_editor.user_id}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_unassign_by_passing_null(self):
        self.paper.assigned_assistant_editor = self.assistant_editor
        self.paper.save()

        self.client.force_authenticate(user=self.editor)
        response = self.client.patch(self.url, {"assistant_editor_id": None}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["assigned_assistant_editor"])
        self.paper.refresh_from_db()
        self.assertIsNone(self.paper.assigned_assistant_editor)
