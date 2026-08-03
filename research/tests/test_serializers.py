from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from committees.models import Committee, CommitteeMember
from research.models import PlagiarismReport, ResearchPaper
from research.serializers import ResearchPaperDetailSerializer

User = get_user_model()


def make_user(email, role='author', **kwargs):
    return User.objects.create(email=email, full_name=email, role=role, specialization='law', **kwargs)


def make_request(user):
    # Mirrors real Django/DRF requests: request.user is AnonymousUser when
    # nobody is logged in, never plain None.
    request = MagicMock()
    request.user = user if user is not None else AnonymousUser()
    return request


class MetaConfigurationTests(TestCase):
    """Documents the exact field/read_only_fields configuration the PUT/DELETE
    finding below depends on."""

    def test_declared_fields(self):
        expected = {
            'id', 'title', 'abstract', 'is_paid_open_access', 'pdf_file',
            'author_name', 'status', 'rejection_reason', 'plagiarism_score', 'specialization',
            'plagiarism_report_id', 'plagiarism_status', 'ai_keywords', 'assistant_editor_report',
            'is_reviewed_by_assistant', 'review_blindness_type',
        }
        self.assertEqual(set(ResearchPaperDetailSerializer.Meta.fields), expected)

    def test_only_review_blindness_type_is_declared_read_only(self):
        self.assertEqual(ResearchPaperDetailSerializer.Meta.read_only_fields, ['review_blindness_type'])

    def test_status_and_is_reviewed_by_assistant_are_writable_at_the_serializer_field_level(self):
        # status and is_reviewed_by_assistant have no read_only override anywhere on the
        # serializer (no SerializerMethodField, no explicit read_only=True), so DRF treats
        # them as normal writable ModelSerializer fields.
        serializer = ResearchPaperDetailSerializer()
        self.assertFalse(serializer.fields['status'].read_only)
        self.assertFalse(serializer.fields['is_reviewed_by_assistant'].read_only)
        self.assertFalse(serializer.fields['rejection_reason'].read_only)
        # Sanity check: review_blindness_type IS read-only as declared.
        self.assertTrue(serializer.fields['review_blindness_type'].read_only)

    def test_is_valid_accepts_status_and_is_reviewed_by_assistant_changes(self):
        author = make_user('author@example.com')
        paper = ResearchPaper.objects.create(
            title='Paper', abstract='a', author=author,
            specialization='law', status=ResearchPaper.Status.SUBMITTED,
        )
        serializer = ResearchPaperDetailSerializer(
            paper,
            data={
                'title': 'Paper', 'abstract': 'a', 'specialization': 'law',
                'status': ResearchPaper.Status.PUBLISHED,
                'is_reviewed_by_assistant': True,
            },
            context={'request': make_request(author)},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['status'], ResearchPaper.Status.PUBLISHED)
        self.assertTrue(serializer.validated_data['is_reviewed_by_assistant'])


class GetAuthorNameTests(TestCase):
    def setUp(self):
        self.author = make_user('author@example.com')
        self.assistant = make_user('assistant@example.com', role='assistant_editor')
        self.editor = make_user('editor@example.com', role='editor')
        self.reviewer = make_user('reviewer@example.com', role='reviewer')
        self.stranger = make_user('stranger@example.com')

    def _paper(self, blindness):
        return ResearchPaper.objects.create(
            title='Paper', abstract='a', author=self.author, specialization='law',
            status=ResearchPaper.Status.SUBMITTED, review_blindness_type=blindness,
            is_reviewed_by_assistant=True,
        )

    def test_unauthenticated_user_sees_anonymous(self):
        paper = self._paper('double_blind')
        serializer = ResearchPaperDetailSerializer(paper, context={'request': make_request(None)})
        self.assertIn('Anonymous', serializer.data['author_name'])

    def test_author_always_sees_own_name(self):
        paper = self._paper('double_blind')
        serializer = ResearchPaperDetailSerializer(paper, context={'request': make_request(self.author)})
        self.assertNotIn('Anonymous', serializer.data['author_name'])

    def test_double_blind_hides_name_from_stranger(self):
        paper = self._paper('double_blind')
        serializer = ResearchPaperDetailSerializer(paper, context={'request': make_request(self.stranger)})
        self.assertIn('Anonymous', serializer.data['author_name'])

    def test_double_blind_reveals_name_to_assistant(self):
        paper = self._paper('double_blind')
        serializer = ResearchPaperDetailSerializer(paper, context={'request': make_request(self.assistant)})
        self.assertNotIn('Anonymous', serializer.data['author_name'])

    def test_single_blind_hides_name_from_reviewer(self):
        paper = self._paper('single_blind')
        # committee/member must be past 'pending' so to_representation's member
        # branch returns the full representation (see
        # test_committee_member_pending_response_drops_author_name_field below
        # for what happens while still pending).
        committee = Committee.objects.create(paper=paper, editor=self.editor, status='approved')
        CommitteeMember.objects.create(committee=committee, user=self.reviewer, role='primary', response='accepted')
        serializer = ResearchPaperDetailSerializer(paper, context={'request': make_request(self.reviewer)})
        self.assertIn('Anonymous', serializer.data['author_name'])

    def test_committee_member_pending_response_drops_author_name_field_entirely(self):
        """
        Documents an inconsistency: the editor-pending restricted-fields branch
        explicitly preserves author_name (filtered_rep['author_name'] = ...),
        but the committee-member-pending branch has no equivalent line, so
        author_name is silently missing from the response instead of being
        anonymized like the rest of the blind-review logic does.
        """
        paper = self._paper('single_blind')
        committee = Committee.objects.create(paper=paper, editor=self.editor)  # status defaults to 'pending'
        CommitteeMember.objects.create(committee=committee, user=self.reviewer, role='primary')  # response defaults to 'pending'
        serializer = ResearchPaperDetailSerializer(paper, context={'request': make_request(self.reviewer)})
        self.assertNotIn('author_name', serializer.data)

    def test_open_review_reveals_name_to_anyone_authenticated(self):
        paper = self._paper('open_review')
        serializer = ResearchPaperDetailSerializer(paper, context={'request': make_request(self.stranger)})
        self.assertNotIn('Anonymous', serializer.data['author_name'])


class ToRepresentationVisibilityTests(TestCase):
    def setUp(self):
        self.author = make_user('author@example.com')
        self.stranger = make_user('stranger@example.com')
        self.assistant = make_user('assistant@example.com', role='assistant_editor')
        self.editor = make_user('editor@example.com', role='editor')

    def test_serializer_crashes_if_context_has_no_request_at_all(self):
        """
        Documents a latent bug in ResearchPaperDetailSerializer.to_representation:
        `user = request.user if request else None` allows `user` to be plain
        None (context.get('request') returns None when no 'request' key is
        supplied at all). configuration.security.can_user_access_pdf then does
        `user.is_authenticated` unconditionally, which raises AttributeError
        on None. In production this path is never hit because every call site
        in research/views.py always passes context={'request': request}, and
        DRF requests always carry AnonymousUser rather than None — but the
        serializer itself has no defense if reused without a request in
        context (e.g. a management command or another app's future caller).
        """
        paper = ResearchPaper.objects.create(
            title='Paper', abstract='a', author=self.author, specialization='law',
            status=ResearchPaper.Status.PUBLISHED,
        )
        serializer = ResearchPaperDetailSerializer(paper, context={})
        with self.assertRaises(AttributeError):
            _ = serializer.data

    def test_unreviewed_paper_hidden_from_unrelated_authenticated_user(self):
        paper = ResearchPaper.objects.create(
            title='Paper', abstract='a', author=self.author, specialization='law',
            status=ResearchPaper.Status.SUBMITTED, is_reviewed_by_assistant=False,
        )
        Committee.objects.create(paper=paper, editor=self.editor)
        serializer = ResearchPaperDetailSerializer(paper, context={'request': make_request(self.editor)})
        self.assertEqual(serializer.data, {})

    def test_assistant_always_sees_full_representation_even_if_unreviewed(self):
        paper = ResearchPaper.objects.create(
            title='Paper', abstract='a', author=self.author, specialization='law',
            status=ResearchPaper.Status.SUBMITTED, is_reviewed_by_assistant=False,
        )
        serializer = ResearchPaperDetailSerializer(paper, context={'request': make_request(self.assistant)})
        self.assertNotEqual(serializer.data, {})
        self.assertEqual(serializer.data['title'], 'Paper')

    def test_editor_with_pending_committee_gets_restricted_fields_only(self):
        paper = ResearchPaper.objects.create(
            title='Paper', abstract='a', author=self.author, specialization='law',
            status=ResearchPaper.Status.SUBMITTED, is_reviewed_by_assistant=True,
        )
        Committee.objects.create(paper=paper, editor=self.editor, status='pending')
        serializer = ResearchPaperDetailSerializer(paper, context={'request': make_request(self.editor)})
        data = serializer.data
        self.assertIsNone(data['pdf_file'])
        self.assertIsNone(data['plagiarism_score'])
        self.assertEqual(data['title'], 'Paper')

    def test_editor_with_approved_committee_gets_full_representation(self):
        paper = ResearchPaper.objects.create(
            title='Paper', abstract='a', author=self.author, specialization='law',
            status=ResearchPaper.Status.SUBMITTED, is_reviewed_by_assistant=True,
        )
        Committee.objects.create(paper=paper, editor=self.editor, status='approved')
        serializer = ResearchPaperDetailSerializer(paper, context={'request': make_request(self.editor)})
        self.assertIn('status', serializer.data)
        self.assertNotIn('pdf_file', [])  # sanity, full rep includes pdf_file key
        self.assertIn('pdf_file', serializer.data)


class PlagiarismMethodFieldTests(TestCase):
    def setUp(self):
        self.author = make_user('author@example.com')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='a', author=self.author,
            specialization='law', status=ResearchPaper.Status.SUBMITTED,
        )

    def test_no_report_returns_none_scores_and_pending_status(self):
        serializer = ResearchPaperDetailSerializer(self.paper, context={'request': make_request(self.author)})
        data = serializer.data
        self.assertIsNone(data['plagiarism_score'])
        self.assertIsNone(data['plagiarism_report_id'])
        self.assertEqual(data['plagiarism_status'], 'pending')
        self.assertEqual(data['ai_keywords'], [])

    def test_existing_report_is_reflected(self):
        report = PlagiarismReport.objects.create(
            paper=self.paper, status=PlagiarismReport.Status.COMPLETED,
            total_similarity_score=42.5, ai_keywords=['x', 'y'],
        )
        serializer = ResearchPaperDetailSerializer(self.paper, context={'request': make_request(self.author)})
        data = serializer.data
        self.assertEqual(data['plagiarism_score'], 42.5)
        self.assertEqual(data['plagiarism_report_id'], report.id)
        self.assertEqual(data['plagiarism_status'], 'completed')
        self.assertEqual(data['ai_keywords'], ['x', 'y'])
