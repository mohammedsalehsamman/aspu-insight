from django.contrib.auth import get_user_model
from django.test import TestCase

from assistantReview.models import AssistantReview
from assistantReview.serializers import (
    AssistantReviewCreateSerializer,
    AssistantReviewSerializer,
)
from research.models import ResearchPaper

User = get_user_model()


class AssistantReviewSerializerTests(TestCase):
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
        self.review = AssistantReview.objects.create(
            paper=self.paper, assistant=self.assistant,
            notes="ok", decision=AssistantReview.Decision.APPROVE,
        )
        self.review.suggested_reviewers.set([self.reviewer])

    def test_all_fields_are_read_only(self):
        serializer = AssistantReviewSerializer(data={
            "paper": self.paper.id, "decision": AssistantReview.Decision.REJECT, "notes": "hacked",
        })
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data, {})

    def test_representation_includes_nested_assistant_and_reviewers(self):
        data = AssistantReviewSerializer(self.review).data

        self.assertEqual(data["decision"], AssistantReview.Decision.APPROVE)
        self.assertEqual(data["assistant"]["user_id"], self.assistant.user_id)
        self.assertEqual(len(data["suggested_reviewers"]), 1)
        self.assertEqual(data["suggested_reviewers"][0]["user_id"], self.reviewer.user_id)


class AssistantReviewCreateSerializerTests(TestCase):
    def setUp(self):
        self.reviewer = User.objects.create(
            email="reviewer@example.com", full_name="Reviewer", role="reviewer", specialization="law",
        )
        self.non_reviewer = User.objects.create(
            email="author@example.com", full_name="Author", role="author", specialization="law",
        )

    def test_valid_minimal_payload(self):
        serializer = AssistantReviewCreateSerializer(data={
            "decision": AssistantReview.Decision.APPROVE,
            "notes": "all good",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_notes_is_required(self):
        serializer = AssistantReviewCreateSerializer(data={
            "decision": AssistantReview.Decision.APPROVE,
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("notes", serializer.errors)

    def test_decision_is_required(self):
        serializer = AssistantReviewCreateSerializer(data={"notes": "n"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("decision", serializer.errors)

    def test_suggested_reviewers_accepts_reviewer_role_users(self):
        serializer = AssistantReviewCreateSerializer(data={
            "decision": AssistantReview.Decision.APPROVE,
            "notes": "n",
            "suggested_reviewers": [self.reviewer.user_id],
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_suggested_reviewers_rejects_non_reviewer_role_users(self):
        serializer = AssistantReviewCreateSerializer(data={
            "decision": AssistantReview.Decision.APPROVE,
            "notes": "n",
            "suggested_reviewers": [self.non_reviewer.user_id],
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("suggested_reviewers", serializer.errors)

    def test_is_format_compliant_and_is_complete_are_not_required(self):
        serializer = AssistantReviewCreateSerializer(data={
            "decision": AssistantReview.Decision.APPROVE,
            "notes": "n",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("is_format_compliant", serializer.validated_data)
        self.assertNotIn("is_complete", serializer.validated_data)
