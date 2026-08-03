from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from assistantReview.models import AssistantReview
from assistantReview.services import AssistantReviewService
from research.models import ResearchPaper
from researchHistory.models import ResearchHistory

User = get_user_model()


class CreateReviewTests(TestCase):
    def setUp(self):
        self.author = User.objects.create(email="author@example.com", full_name="Author", specialization="law")
        self.assistant = User.objects.create(
            email="assistant@example.com", full_name="Assistant", role="assistant_editor", specialization="law",
        )
        self.reviewer = User.objects.create(
            email="reviewer@example.com", full_name="Reviewer", role="reviewer", specialization="law",
        )
        self.paper = ResearchPaper.objects.create(
            title="Paper", abstract="abstract", author=self.author,
            specialization="law", status=ResearchPaper.Status.SUBMITTED,
        )

    def test_rejects_review_when_paper_not_awaiting_review(self):
        self.paper.status = ResearchPaper.Status.PUBLISHED
        self.paper.save()

        with self.assertRaises(ValidationError):
            AssistantReviewService.create_review(
                self.paper, self.assistant,
                {"decision": AssistantReview.Decision.APPROVE, "notes": ""},
            )

    def test_approve_moves_paper_to_editor_review(self):
        self.paper.rejection_reason = "old reason"
        self.paper.save()

        review = AssistantReviewService.create_review(
            self.paper, self.assistant,
            {"decision": AssistantReview.Decision.APPROVE, "notes": "all good", "suggested_reviewers": [self.reviewer]},
        )

        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.EDITOR_REVIEW)
        self.assertTrue(self.paper.is_reviewed_by_assistant)
        self.assertEqual(self.paper.rejection_reason, "")
        self.assertEqual(list(review.suggested_reviewers.all()), [self.reviewer])

    def test_reject_moves_paper_to_revision_required_with_reason(self):
        AssistantReviewService.create_review(
            self.paper, self.assistant,
            {"decision": AssistantReview.Decision.REJECT, "notes": "needs formatting fixes"},
        )

        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.REVISION_REQUIRED)
        self.assertEqual(self.paper.rejection_reason, "needs formatting fixes")
        self.assertFalse(self.paper.is_reviewed_by_assistant)

    def test_creates_history_entry_reflecting_transition(self):
        AssistantReviewService.create_review(
            self.paper, self.assistant,
            {"decision": AssistantReview.Decision.APPROVE, "notes": "ok"},
        )

        history = ResearchHistory.objects.get(paper=self.paper)
        self.assertEqual(history.from_status, ResearchPaper.Status.SUBMITTED)
        self.assertEqual(history.to_status, ResearchPaper.Status.EDITOR_REVIEW)
        self.assertEqual(history.changed_by, self.assistant)
        self.assertEqual(history.note, "ok")
