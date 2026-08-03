from django.contrib.auth import get_user_model
from django.test import TestCase

from research.models import ResearchPaper
from researchHistory.models import ResearchHistory
from researchHistory.serializers import ResearchHistorySerializer

User = get_user_model()


def make_user(email, role='author', **kwargs):
    return User.objects.create(email=email, full_name=email, role=role, specialization='law', **kwargs)


class ResearchHistorySerializerTests(TestCase):
    def setUp(self):
        self.author = make_user('author@example.com')
        self.editor = make_user('editor@example.com', role='editor')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='a', author=self.author, specialization='law',
        )
        self.history = ResearchHistory.objects.create(
            paper=self.paper,
            from_status=ResearchPaper.Status.SUBMITTED,
            to_status=ResearchPaper.Status.EDITOR_REVIEW,
            changed_by=self.editor,
            note='moved to editor review',
        )

    def test_declared_fields(self):
        expected = {'id', 'paper', 'from_status', 'to_status', 'changed_by', 'note', 'created_at'}
        self.assertEqual(set(ResearchHistorySerializer.Meta.fields), expected)

    def test_all_fields_are_read_only(self):
        self.assertEqual(
            set(ResearchHistorySerializer.Meta.read_only_fields),
            set(ResearchHistorySerializer.Meta.fields),
        )

    def test_serializes_expected_values(self):
        serializer = ResearchHistorySerializer(self.history)
        data = serializer.data
        self.assertEqual(data['paper'], self.paper.id)
        self.assertEqual(data['from_status'], ResearchPaper.Status.SUBMITTED)
        self.assertEqual(data['to_status'], ResearchPaper.Status.EDITOR_REVIEW)
        self.assertEqual(data['note'], 'moved to editor review')
        self.assertEqual(data['changed_by']['email'], 'editor@example.com')

    def test_changed_by_uses_nested_user_list_serializer(self):
        serializer = ResearchHistorySerializer(self.history)
        changed_by = serializer.data['changed_by']
        self.assertIn('user_id', changed_by)
        self.assertIn('full_name', changed_by)
        self.assertIn('role', changed_by)

    def test_changed_by_null_when_not_set(self):
        history = ResearchHistory.objects.create(
            paper=self.paper,
            from_status=ResearchPaper.Status.PENDING,
            to_status=ResearchPaper.Status.SUBMITTED,
        )
        serializer = ResearchHistorySerializer(history)
        self.assertIsNone(serializer.data['changed_by'])

    def test_serializer_is_read_only_and_ignores_write_attempts(self):
        # Attempting to "write" through this serializer must not raise and must
        # not be usable to create/update anything meaningful, since every field
        # is declared read_only.
        serializer = ResearchHistorySerializer(data={
            'paper': self.paper.id,
            'from_status': 'x',
            'to_status': 'y',
            'note': 'attempted write',
        })
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data, {})
