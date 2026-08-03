from django.contrib.auth import get_user_model
from django.test import TestCase

from editorReview.models import EditorReview
from editorReview.serializers import (
    EditorFinalReviewSerializer,
    EditorInitialReviewSerializer,
    EditorReviewSerializer,
)
from research.models import ResearchPaper

User = get_user_model()


class EditorReviewSerializerTests(TestCase):
    def setUp(self):
        self.author = User.objects.create(email="author@example.com", full_name="Author", specialization="law")
        self.editor = User.objects.create(
            email="editor@example.com", full_name="Editor", role="editor", specialization="law",
        )
        self.paper = ResearchPaper.objects.create(
            title="Paper", abstract="abstract", author=self.author,
            specialization="law", status=ResearchPaper.Status.COMMITTEE_REVIEW,
        )
        self.review = EditorReview.objects.create(
            paper=self.paper, editor=self.editor, stage=EditorReview.Stage.INITIAL,
            notes="ok", decision=EditorReview.Decision.SEND_TO_COMMITTEE,
        )

    def test_all_fields_are_read_only(self):
        serializer = EditorReviewSerializer(data={
            "paper": self.paper.id, "decision": EditorReview.Decision.REJECT, "notes": "hacked",
        })
        # Every declared field is read-only, so validated_data stays empty
        # regardless of what is supplied.
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data, {})

    def test_representation_includes_nested_editor(self):
        serializer = EditorReviewSerializer(self.review)
        data = serializer.data

        self.assertEqual(data["decision"], EditorReview.Decision.SEND_TO_COMMITTEE)
        self.assertEqual(data["editor"]["user_id"], self.editor.user_id)
        self.assertEqual(data["editor"]["email"], self.editor.email)
        self.assertEqual(data["paper"], self.paper.id)


class EditorInitialReviewSerializerTests(TestCase):
    def test_valid_decision_passes(self):
        serializer = EditorInitialReviewSerializer(data={
            "decision": EditorReview.Decision.SEND_TO_COMMITTEE,
            "notes": "looks fine",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_revision_required_and_reject_are_allowed(self):
        for decision in (EditorReview.Decision.REVISION_REQUIRED, EditorReview.Decision.REJECT):
            serializer = EditorInitialReviewSerializer(data={"decision": decision, "notes": "n"})
            self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_accept_decision_is_rejected(self):
        serializer = EditorInitialReviewSerializer(data={
            "decision": EditorReview.Decision.ACCEPT,
            "notes": "trying to accept early",
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("decision", serializer.errors)

    def test_notes_is_required(self):
        serializer = EditorInitialReviewSerializer(data={
            "decision": EditorReview.Decision.SEND_TO_COMMITTEE,
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("notes", serializer.errors)

    def test_ieee_report_is_optional(self):
        serializer = EditorInitialReviewSerializer(data={
            "decision": EditorReview.Decision.SEND_TO_COMMITTEE,
            "notes": "n",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("ieee_report", serializer.validated_data)


class EditorFinalReviewSerializerTests(TestCase):
    def test_send_to_committee_decision_is_rejected(self):
        serializer = EditorFinalReviewSerializer(data={
            "decision": EditorReview.Decision.SEND_TO_COMMITTEE,
            "notes": "n",
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("decision", serializer.errors)

    def test_accept_without_full_checklist_fails_validation(self):
        serializer = EditorFinalReviewSerializer(data={
            "decision": EditorReview.Decision.ACCEPT,
            "notes": "n",
            "language_review_passed": True,
            "citation_check_passed": True,
            "publisher_permission_obtained": False,
        })
        self.assertFalse(serializer.is_valid())

    def test_accept_with_full_checklist_passes(self):
        serializer = EditorFinalReviewSerializer(data={
            "decision": EditorReview.Decision.ACCEPT,
            "notes": "n",
            "language_review_passed": True,
            "citation_check_passed": True,
            "publisher_permission_obtained": True,
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_revision_required_does_not_need_checklist(self):
        serializer = EditorFinalReviewSerializer(data={
            "decision": EditorReview.Decision.REVISION_REQUIRED,
            "notes": "please revise",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_reject_does_not_need_checklist(self):
        serializer = EditorFinalReviewSerializer(data={
            "decision": EditorReview.Decision.REJECT,
            "notes": "not suitable",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
