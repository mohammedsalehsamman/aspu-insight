from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from assistantReview.models import AssistantReview
from research.models import ResearchPaper

User = get_user_model()


class AssistantReviewAPIViewTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create(
            email="author@example.com", full_name="Author", specialization="law", email_verified=True,
        )
        self.assistant = User.objects.create(
            email="assistant@example.com", full_name="Assistant", role="assistant_editor", specialization="law",
            email_verified=True,
        )
        self.admin = User.objects.create(
            email="admin@example.com", full_name="Admin", role="admin", specialization="law", email_verified=True,
        )
        self.reviewer = User.objects.create(
            email="reviewer@example.com", full_name="Reviewer", role="reviewer", specialization="law",
            email_verified=True,
        )
        self.non_reviewer = User.objects.create(
            email="notreviewer@example.com", full_name="Not Reviewer", role="editor", specialization="law",
            email_verified=True,
        )
        self.paper = ResearchPaper.objects.create(
            title="Paper", abstract="abstract", author=self.author,
            specialization="law", status=ResearchPaper.Status.SUBMITTED,
        )
        self.url = reverse("assistant-review", kwargs={"paper_id": self.paper.id})

    def test_unauthenticated_cannot_access(self):
        response = self.client.post(self.url, {"decision": "APPROVE", "notes": "n"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_assistant_editor_role_forbidden(self):
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.post(self.url, {"decision": "APPROVE", "notes": "n"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_role_allowed(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(self.url, {"decision": "APPROVE", "notes": "n"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_assistant_editor_can_approve(self):
        self.client.force_authenticate(user=self.assistant)
        response = self.client.post(self.url, {
            "decision": "APPROVE",
            "notes": "looks good",
            "suggested_reviewers": [self.reviewer.user_id],
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.EDITOR_REVIEW)
        self.assertTrue(self.paper.is_reviewed_by_assistant)

    def test_assistant_editor_can_reject(self):
        self.client.force_authenticate(user=self.assistant)
        response = self.client.post(self.url, {"decision": "REJECT", "notes": "needs formatting fixes"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.REVISION_REQUIRED)
        self.assertEqual(self.paper.rejection_reason, "needs formatting fixes")

    def test_paper_not_awaiting_assistant_review_returns_400(self):
        self.paper.status = ResearchPaper.Status.PUBLISHED
        self.paper.save()

        self.client.force_authenticate(user=self.assistant)
        response = self.client.post(self.url, {"decision": "APPROVE", "notes": "n"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_suggested_reviewer_must_have_reviewer_role(self):
        self.client.force_authenticate(user=self.assistant)
        response = self.client.post(self.url, {
            "decision": "APPROVE",
            "notes": "n",
            "suggested_reviewers": [self.non_reviewer.user_id],
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_lists_reviews_for_paper(self):
        AssistantReview.objects.create(
            paper=self.paper, assistant=self.assistant, notes="n", decision=AssistantReview.Decision.APPROVE,
        )

        self.client.force_authenticate(user=self.assistant)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_editor_can_read_reports(self):
        AssistantReview.objects.create(
            paper=self.paper, assistant=self.assistant, notes="n", decision=AssistantReview.Decision.APPROVE,
        )

        self.client.force_authenticate(user=self.non_reviewer)  # role="editor"
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_editor_cannot_post_reports(self):
        self.client.force_authenticate(user=self.non_reviewer)  # role="editor"
        response = self.client.post(self.url, {"decision": "APPROVE", "notes": "n"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_forbidden_for_unrelated_role(self):
        self.client.force_authenticate(user=self.reviewer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
