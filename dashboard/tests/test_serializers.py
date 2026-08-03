from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from research.models import ResearchPaper
from researchHistory.models import ResearchHistory
from dashboard.serializers import (
    AdminResearchPaperSerializer,
    AdminResearchPaperDetailSerializer,
    AssignEditorSerializer,
)


class AdminResearchPaperSerializerTest(TestCase):
    def setUp(self):
        self.author = User.objects.create(
            email="author@example.com", full_name="Author", role="author", specialization="law",
        )
        self.editor = User.objects.create(
            email="editor@example.com", full_name="Editor", role="editor", specialization="law",
        )
        self.paper = ResearchPaper.objects.create(
            title="Test Paper",
            abstract="abstract text",
            author=self.author,
            assigned_editor=self.editor,
            specialization="law",
            status=ResearchPaper.Status.SUBMITTED,
        )

    def test_serializes_expected_fields(self):
        data = AdminResearchPaperSerializer(self.paper).data

        self.assertEqual(data['id'], self.paper.id)
        self.assertEqual(data['title'], "Test Paper")
        self.assertEqual(data['status'], ResearchPaper.Status.SUBMITTED)
        self.assertEqual(data['author']['email'], "author@example.com")
        self.assertEqual(data['assigned_editor']['email'], "editor@example.com")
        self.assertNotIn('pdf_file', data)

    def test_assigned_editor_null_when_unassigned(self):
        paper = ResearchPaper.objects.create(
            title="No editor", abstract="x", author=self.author, specialization="law",
        )
        data = AdminResearchPaperSerializer(paper).data
        self.assertIsNone(data['assigned_editor'])

    def test_fields_are_read_only(self):
        serializer = AdminResearchPaperSerializer()
        for field_name in AdminResearchPaperSerializer.Meta.fields:
            self.assertTrue(serializer.fields[field_name].read_only)


class AdminResearchPaperDetailSerializerTest(TestCase):
    def setUp(self):
        self.author = User.objects.create(
            email="author2@example.com", full_name="Author2", role="author", specialization="law",
        )
        self.editor = User.objects.create(
            email="editor2@example.com", full_name="Editor2", role="editor", specialization="law",
        )
        self.paper = ResearchPaper.objects.create(
            title="Detail Paper", abstract="abstract", author=self.author, specialization="law",
        )

    def test_includes_history_ordered_desc_and_limited_to_ten(self):
        base_time = timezone.now()
        for i in range(12):
            entry = ResearchHistory.objects.create(
                paper=self.paper,
                from_status="submitted",
                to_status="editor_review",
                changed_by=self.editor,
                note=f"note {i}",
            )
            # created_at is auto_now_add; force distinct, increasing timestamps
            # so ordering isn't left to depend on insertion-order tie-breaking.
            ResearchHistory.objects.filter(pk=entry.pk).update(
                created_at=base_time + timedelta(seconds=i)
            )

        data = AdminResearchPaperDetailSerializer(self.paper).data

        self.assertIn('history', data)
        self.assertEqual(len(data['history']), 10)
        # newest first (last created note should be first)
        self.assertEqual(data['history'][0]['note'], "note 11")

    def test_history_empty_when_no_records(self):
        data = AdminResearchPaperDetailSerializer(self.paper).data
        self.assertEqual(data['history'], [])


class AssignEditorSerializerTest(TestCase):
    def test_valid_with_integer_editor_id(self):
        serializer = AssignEditorSerializer(data={"editor_id": 5})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['editor_id'], 5)

    def test_valid_with_null_editor_id(self):
        serializer = AssignEditorSerializer(data={"editor_id": None})
        self.assertTrue(serializer.is_valid())
        self.assertIsNone(serializer.validated_data['editor_id'])

    def test_invalid_when_editor_id_missing(self):
        serializer = AssignEditorSerializer(data={})
        self.assertFalse(serializer.is_valid())
        self.assertIn('editor_id', serializer.errors)

    def test_invalid_when_editor_id_not_an_integer(self):
        serializer = AssignEditorSerializer(data={"editor_id": "not-a-number"})
        self.assertFalse(serializer.is_valid())
        self.assertIn('editor_id', serializer.errors)
