from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import NotFound, ValidationError

from editorReview.models import EditorReview
from editorReview.services import EditorReviewService
from notifications.models import Notification
from research.models import ResearchPaper
from researchHistory.models import ResearchHistory

User = get_user_model()


class CreateInitialReviewTests(TestCase):
    def setUp(self):
        self.author = User.objects.create(email="author@example.com", full_name="Author", specialization="law")
        self.editor = User.objects.create(
            email="editor@example.com", full_name="Editor", role="editor", specialization="law",
        )
        self.other_editor = User.objects.create(
            email="editor2@example.com", full_name="Editor Two", role="editor", specialization="law",
        )
        self.admin = User.objects.create(
            email="admin@example.com", full_name="Admin", role="admin", specialization="law",
        )
        self.paper = ResearchPaper.objects.create(
            title="Paper", abstract="abstract", author=self.author,
            specialization="law", status=ResearchPaper.Status.EDITOR_REVIEW,
        )

    def test_rejects_review_when_paper_not_awaiting_editor_review(self):
        self.paper.status = ResearchPaper.Status.SUBMITTED
        self.paper.save()

        with self.assertRaises(ValidationError):
            EditorReviewService.create_initial_review(
                self.paper, self.editor,
                {"decision": EditorReview.Decision.SEND_TO_COMMITTEE, "notes": ""},
            )

    def test_rejects_invalid_decision_for_initial_review(self):
        with self.assertRaises(ValidationError):
            EditorReviewService.create_initial_review(
                self.paper, self.editor,
                {"decision": EditorReview.Decision.ACCEPT, "notes": "trying to accept early"},
            )

    def test_send_to_committee_moves_paper_to_committee_review(self):
        self.paper.rejection_reason = "old reason"
        self.paper.save()

        review = EditorReviewService.create_initial_review(
            self.paper, self.editor,
            {"decision": EditorReview.Decision.SEND_TO_COMMITTEE, "notes": "looks fine"},
        )

        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.COMMITTEE_REVIEW)
        self.assertEqual(self.paper.rejection_reason, "")
        self.assertEqual(review.stage, EditorReview.Stage.INITIAL)
        self.assertEqual(review.editor, self.editor)

    def test_revision_required_sets_rejection_reason(self):
        EditorReviewService.create_initial_review(
            self.paper, self.editor,
            {"decision": EditorReview.Decision.REVISION_REQUIRED, "notes": "needs formatting fixes"},
        )

        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.REVISION_REQUIRED)
        self.assertEqual(self.paper.rejection_reason, "needs formatting fixes")

    def test_reject_sets_rejection_reason_and_status(self):
        EditorReviewService.create_initial_review(
            self.paper, self.editor,
            {"decision": EditorReview.Decision.REJECT, "notes": "out of scope"},
        )

        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.REJECTED)
        self.assertEqual(self.paper.rejection_reason, "out of scope")

    def test_creates_history_entry_reflecting_transition(self):
        EditorReviewService.create_initial_review(
            self.paper, self.editor,
            {"decision": EditorReview.Decision.SEND_TO_COMMITTEE, "notes": "ok"},
        )

        history = ResearchHistory.objects.get(paper=self.paper)
        self.assertEqual(history.from_status, ResearchPaper.Status.EDITOR_REVIEW)
        self.assertEqual(history.to_status, ResearchPaper.Status.COMMITTEE_REVIEW)
        self.assertEqual(history.changed_by, self.editor)
        self.assertEqual(history.note, "ok")

    def test_rejects_when_paper_assigned_to_different_editor(self):
        self.paper.assigned_editor = self.other_editor
        self.paper.save()

        with self.assertRaises(ValidationError):
            EditorReviewService.create_initial_review(
                self.paper, self.editor,
                {"decision": EditorReview.Decision.SEND_TO_COMMITTEE, "notes": ""},
            )

    def test_assigned_editor_can_review_own_paper(self):
        self.paper.assigned_editor = self.editor
        self.paper.save()

        review = EditorReviewService.create_initial_review(
            self.paper, self.editor,
            {"decision": EditorReview.Decision.SEND_TO_COMMITTEE, "notes": ""},
        )

        self.assertIsNotNone(review.pk)

    def test_admin_can_review_paper_assigned_to_other_editor(self):
        self.paper.assigned_editor = self.other_editor
        self.paper.save()

        review = EditorReviewService.create_initial_review(
            self.paper, self.admin,
            {"decision": EditorReview.Decision.SEND_TO_COMMITTEE, "notes": ""},
        )

        self.assertIsNotNone(review.pk)


class CreateFinalReviewTests(TestCase):
    def setUp(self):
        self.author = User.objects.create(email="author@example.com", full_name="Author", specialization="law")
        self.editor = User.objects.create(
            email="editor@example.com", full_name="Editor", role="editor", specialization="law",
        )
        self.other_editor = User.objects.create(
            email="editor2@example.com", full_name="Editor Two", role="editor", specialization="law",
        )
        self.paper = ResearchPaper.objects.create(
            title="Paper", abstract="abstract", author=self.author,
            specialization="law", status=ResearchPaper.Status.COMMITTEE_REVIEW,
        )

    def test_rejects_review_when_paper_not_awaiting_final_review(self):
        self.paper.status = ResearchPaper.Status.EDITOR_REVIEW
        self.paper.save()

        with self.assertRaises(ValidationError):
            EditorReviewService.create_final_review(
                self.paper, self.editor,
                {"decision": EditorReview.Decision.ACCEPT, "notes": ""},
            )

    def test_rejects_invalid_decision_for_final_review(self):
        with self.assertRaises(ValidationError):
            EditorReviewService.create_final_review(
                self.paper, self.editor,
                {"decision": EditorReview.Decision.SEND_TO_COMMITTEE, "notes": ""},
            )

    def test_accept_requires_full_checklist(self):
        with self.assertRaises(ValidationError):
            EditorReviewService.create_final_review(
                self.paper, self.editor,
                {
                    "decision": EditorReview.Decision.ACCEPT,
                    "notes": "",
                    "language_review_passed": True,
                    "citation_check_passed": True,
                    "publisher_permission_obtained": False,
                },
            )

    def test_accept_with_full_checklist_moves_paper_to_accepted(self):
        review = EditorReviewService.create_final_review(
            self.paper, self.editor,
            {
                "decision": EditorReview.Decision.ACCEPT,
                "notes": "all good",
                "language_review_passed": True,
                "citation_check_passed": True,
                "publisher_permission_obtained": True,
            },
        )

        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.ACCEPTED)
        self.assertEqual(review.stage, EditorReview.Stage.FINAL)

    def test_revision_required_does_not_need_checklist(self):
        EditorReviewService.create_final_review(
            self.paper, self.editor,
            {"decision": EditorReview.Decision.REVISION_REQUIRED, "notes": "please revise"},
        )

        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.REVISION_REQUIRED)
        self.assertEqual(self.paper.rejection_reason, "please revise")

    def test_reject_sets_status_and_reason(self):
        EditorReviewService.create_final_review(
            self.paper, self.editor,
            {"decision": EditorReview.Decision.REJECT, "notes": "not suitable"},
        )

        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.REJECTED)
        self.assertEqual(self.paper.rejection_reason, "not suitable")

    def test_creates_history_entry_reflecting_transition(self):
        EditorReviewService.create_final_review(
            self.paper, self.editor,
            {
                "decision": EditorReview.Decision.ACCEPT,
                "notes": "great",
                "language_review_passed": True,
                "citation_check_passed": True,
                "publisher_permission_obtained": True,
            },
        )

        history = ResearchHistory.objects.get(paper=self.paper)
        self.assertEqual(history.from_status, ResearchPaper.Status.COMMITTEE_REVIEW)
        self.assertEqual(history.to_status, ResearchPaper.Status.ACCEPTED)
        self.assertEqual(history.changed_by, self.editor)
        self.assertEqual(history.note, "great")

    def test_rejects_when_paper_assigned_to_different_editor(self):
        self.paper.assigned_editor = self.other_editor
        self.paper.save()

        with self.assertRaises(ValidationError):
            EditorReviewService.create_final_review(
                self.paper, self.editor,
                {"decision": EditorReview.Decision.REJECT, "notes": ""},
            )


class PublishPaperTests(TestCase):
    def setUp(self):
        self.author = User.objects.create(email="author@example.com", full_name="Author", specialization="law")
        self.editor = User.objects.create(
            email="editor@example.com", full_name="Editor", role="editor", specialization="law",
        )
        self.paper = ResearchPaper.objects.create(
            title="Paper", abstract="abstract", author=self.author,
            specialization="law", status=ResearchPaper.Status.ACCEPTED,
        )

    def test_rejects_publish_when_paper_not_accepted(self):
        self.paper.status = ResearchPaper.Status.COMMITTEE_REVIEW
        self.paper.save()

        with self.assertRaises(ValidationError):
            EditorReviewService.publish_paper(self.paper, self.editor)

    def test_publish_moves_paper_to_published(self):
        paper = EditorReviewService.publish_paper(self.paper, self.editor)

        self.assertEqual(paper.status, ResearchPaper.Status.PUBLISHED)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.PUBLISHED)

    def test_publish_creates_history_entry(self):
        EditorReviewService.publish_paper(self.paper, self.editor)

        history = ResearchHistory.objects.get(paper=self.paper)
        self.assertEqual(history.from_status, ResearchPaper.Status.ACCEPTED)
        self.assertEqual(history.to_status, ResearchPaper.Status.PUBLISHED)
        self.assertEqual(history.changed_by, self.editor)
        self.assertEqual(history.note, "Published")


class AssignAssistantEditorTests(TestCase):
    def setUp(self):
        self.author = User.objects.create(email="author@example.com", full_name="Author", specialization="law")
        self.editor = User.objects.create(
            email="editor@example.com", full_name="Editor", role="editor", specialization="law",
        )
        self.other_editor = User.objects.create(
            email="editor2@example.com", full_name="Editor Two", role="editor", specialization="law",
        )
        self.admin = User.objects.create(
            email="admin@example.com", full_name="Admin", role="admin", specialization="law",
        )
        self.assistant_editor = User.objects.create(
            email="assistant@example.com", full_name="Assistant", role="assistant_editor", specialization="law",
        )
        self.reviewer = User.objects.create(
            email="reviewer@example.com", full_name="Reviewer", role="reviewer", specialization="law",
        )
        self.paper = ResearchPaper.objects.create(
            title="Paper", abstract="abstract", author=self.author,
            specialization="law", status=ResearchPaper.Status.SUBMITTED,
        )

    def test_editor_can_assign_assistant_editor(self):
        paper = EditorReviewService.assign_assistant_editor(
            self.paper, self.editor, self.assistant_editor.user_id,
        )

        self.assertEqual(paper.assigned_assistant_editor, self.assistant_editor)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.assigned_assistant_editor, self.assistant_editor)

    def test_assigning_notifies_the_assistant_editor(self):
        EditorReviewService.assign_assistant_editor(
            self.paper, self.editor, self.assistant_editor.user_id,
        )

        notification = Notification.objects.get(recipient=self.assistant_editor)
        self.assertEqual(
            notification.notification_type,
            Notification.NotificationType.ASSISTANT_EDITOR_ASSIGNED,
        )
        self.assertEqual(notification.actor, self.editor)

    def test_rejects_target_user_that_is_not_an_assistant_editor(self):
        with self.assertRaises(NotFound):
            EditorReviewService.assign_assistant_editor(
                self.paper, self.editor, self.reviewer.user_id,
            )

    def test_rejects_nonexistent_target_user(self):
        with self.assertRaises(NotFound):
            EditorReviewService.assign_assistant_editor(
                self.paper, self.editor, 999999,
            )

    def test_rejects_when_paper_assigned_to_different_editor(self):
        self.paper.assigned_editor = self.other_editor
        self.paper.save()

        with self.assertRaises(ValidationError):
            EditorReviewService.assign_assistant_editor(
                self.paper, self.editor, self.assistant_editor.user_id,
            )

    def test_admin_can_assign_for_paper_assigned_to_other_editor(self):
        self.paper.assigned_editor = self.other_editor
        self.paper.save()

        paper = EditorReviewService.assign_assistant_editor(
            self.paper, self.admin, self.assistant_editor.user_id,
        )

        self.assertEqual(paper.assigned_assistant_editor, self.assistant_editor)

    def test_can_unassign_by_passing_none(self):
        self.paper.assigned_assistant_editor = self.assistant_editor
        self.paper.save()

        paper = EditorReviewService.assign_assistant_editor(
            self.paper, self.editor, None,
        )

        self.assertIsNone(paper.assigned_assistant_editor)
