from django.contrib.auth import get_user_model
from django.test import TestCase

from research.models import ResearchPaper
from researchHistory.models import ResearchHistory
from researchHistory.services import log_status_change

User = get_user_model()


class LogStatusChangeTests(TestCase):
    def setUp(self):
        self.author = User.objects.create(email="author@example.com", full_name="Author", specialization="law")
        self.editor = User.objects.create(email="editor@example.com", full_name="Editor", role="editor", specialization="law")
        self.paper = ResearchPaper.objects.create(title="Paper", abstract="abstract", author=self.author, specialization="law")

    def test_creates_history_entry_with_given_fields(self):
        entry = log_status_change(
            self.paper, ResearchPaper.Status.SUBMITTED, ResearchPaper.Status.EDITOR_REVIEW,
            changed_by=self.editor, note="looks good",
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry.paper, self.paper)
        self.assertEqual(entry.from_status, ResearchPaper.Status.SUBMITTED)
        self.assertEqual(entry.to_status, ResearchPaper.Status.EDITOR_REVIEW)
        self.assertEqual(entry.changed_by, self.editor)
        self.assertEqual(entry.note, "looks good")
        self.assertEqual(ResearchHistory.objects.count(), 1)

    def test_no_op_when_status_unchanged(self):
        entry = log_status_change(
            self.paper, ResearchPaper.Status.SUBMITTED, ResearchPaper.Status.SUBMITTED,
        )
        self.assertIsNone(entry)
        self.assertEqual(ResearchHistory.objects.count(), 0)

    def test_changed_by_and_note_are_optional(self):
        entry = log_status_change(self.paper, ResearchPaper.Status.SUBMITTED, ResearchPaper.Status.REJECTED)
        self.assertIsNone(entry.changed_by)
        self.assertEqual(entry.note, "")
