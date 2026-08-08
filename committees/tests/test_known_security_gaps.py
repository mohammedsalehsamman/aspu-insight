from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from committees.models import Committee, CommitteeMember
from committees.services import CommitteeService
from research.models import ResearchPaper

User = get_user_model()


def make_user(email, role, **kwargs):
    kwargs.setdefault('email_verified', True)
    return User.objects.create(email=email, full_name=email.split('@')[0], role=role, specialization='law', **kwargs)


class GetAvailableReviewersAssignedEditorTests(TestCase):
    """Same bug class as editorReview's publish_paper(): an editor who is not the paper's
    assigned_editor should not be able to act on it — get_available_reviewers() only checked
    role == 'editor', never assigned_editor, so any editor could probe reviewer lists for any
    paper in the system, not just papers assigned to them."""

    def setUp(self):
        self.author = make_user('author@example.com', 'author')
        self.assigned_editor = make_user('assigned@example.com', 'editor')
        self.other_editor = make_user('other@example.com', 'editor')
        self.reviewer = make_user('reviewer@example.com', 'reviewer')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
            assigned_editor=self.assigned_editor,
        )

    def test_editor_not_assigned_to_paper_is_rejected(self):
        with self.assertRaises(ValidationError):
            CommitteeService.get_available_reviewers(self.other_editor, self.paper.id)

    def test_assigned_editor_is_allowed(self):
        result = CommitteeService.get_available_reviewers(self.assigned_editor, self.paper.id)
        self.assertIn(self.reviewer, result)

    def test_admin_bypasses_assignment(self):
        # get_available_reviewers()'s own role gate only lets role=='editor' or is_staff
        # through in the first place (unrelated to the assigned_editor check being tested
        # here) — is_staff=True reaches that gate, role='admin' is what check_assigned_editor
        # itself treats as a bypass.
        admin = make_user('admin@example.com', 'admin', is_staff=True)
        result = CommitteeService.get_available_reviewers(admin, self.paper.id)
        self.assertIn(self.reviewer, result)

    def test_unassigned_paper_allows_any_editor(self):
        unassigned_paper = ResearchPaper.objects.create(
            title='Unassigned', abstract='abstract', author=self.author, specialization='law',
        )
        result = CommitteeService.get_available_reviewers(self.other_editor, unassigned_paper.id)
        self.assertIn(self.reviewer, result)


class CreateCommitteeAssignedEditorTests(TestCase):
    def setUp(self):
        self.author = make_user('author2@example.com', 'author')
        self.assigned_editor = make_user('assigned2@example.com', 'editor')
        self.other_editor = make_user('other2@example.com', 'editor')
        self.reviewers = [make_user(f'rev2-{i}@example.com', 'reviewer') for i in range(5)]
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
            assigned_editor=self.assigned_editor,
        )
        self.primary_ids = [r.user_id for r in self.reviewers[:3]]
        self.substitute_ids = [r.user_id for r in self.reviewers[3:5]]

    def test_editor_not_assigned_to_paper_cannot_create_committee(self):
        with self.assertRaises(ValidationError):
            CommitteeService.create_committee(
                self.other_editor, self.paper.id, self.primary_ids, self.substitute_ids, 'single_blind',
            )
        self.assertFalse(Committee.objects.filter(paper=self.paper).exists())

    def test_assigned_editor_can_create_committee(self):
        committee = CommitteeService.create_committee(
            self.assigned_editor, self.paper.id, self.primary_ids, self.substitute_ids, 'single_blind',
        )
        self.assertEqual(committee.paper_id, self.paper.id)


class GetResearchPaperDetailsUnrelatedUserTests(TestCase):
    """get_research_paper_details() returned title/abstract/status/rejection_reason to any
    authenticated user regardless of their relationship to the paper — only author_name/pdf_file
    were conditionally blinded. Any authenticated user (any role) could read the editorial
    status/rejection_reason of any other user's paper, published or not."""

    def setUp(self):
        self.author = make_user('author3@example.com', 'author')
        self.stranger = make_user('stranger@example.com', 'reviewer')
        self.assigned_editor = make_user('assigned3@example.com', 'editor')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
            assigned_editor=self.assigned_editor, rejection_reason='needs more citations',
        )

    def test_unrelated_authenticated_user_is_denied(self):
        from rest_framework.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            CommitteeService.get_research_paper_details(self.stranger, self.paper.id)

    def test_author_can_view_own_paper(self):
        data, _ = CommitteeService.get_research_paper_details(self.author, self.paper.id)
        self.assertEqual(data['id'], self.paper.id)

    def test_assigned_editor_can_view(self):
        data, _ = CommitteeService.get_research_paper_details(self.assigned_editor, self.paper.id)
        self.assertEqual(data['rejection_reason'], 'needs more citations')

    def test_committee_member_can_view(self):
        committee = Committee.objects.create(paper=self.paper, editor=self.assigned_editor, status='pending')
        member_reviewer = make_user('member@example.com', 'reviewer')
        CommitteeMember.objects.create(committee=committee, user=member_reviewer, role='primary')
        data, _ = CommitteeService.get_research_paper_details(member_reviewer, self.paper.id)
        self.assertEqual(data['id'], self.paper.id)
