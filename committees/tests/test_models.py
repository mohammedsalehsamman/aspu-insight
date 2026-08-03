from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from committees.models import Committee, CommitteeMember
from research.models import ResearchPaper

User = get_user_model()


def make_user(email, role, **kwargs):
    return User.objects.create(email=email, full_name=email.split('@')[0], role=role, specialization='law', **kwargs)


class CommitteeModelTests(TestCase):
    def setUp(self):
        self.editor = make_user('editor@example.com', 'editor')
        self.author = make_user('author@example.com', 'author')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
        )

    def test_deadline_defaults_to_settings_days_from_now(self):
        before = timezone.now()
        committee = Committee.objects.create(paper=self.paper, editor=self.editor)
        after = timezone.now()
        self.assertIsNotNone(committee.deadline)
        self.assertGreaterEqual(committee.deadline, before + timezone.timedelta(days=14, hours=23))
        self.assertLessEqual(committee.deadline, after + timezone.timedelta(days=15, minutes=1))

    @override_settings(COMMITTEE_DEADLINE_DAYS=3)
    def test_deadline_respects_custom_setting(self):
        before = timezone.now()
        committee = Committee.objects.create(paper=self.paper, editor=self.editor)
        self.assertLessEqual(committee.deadline, before + timezone.timedelta(days=3, minutes=1))

    def test_explicit_deadline_is_not_overwritten(self):
        custom_deadline = timezone.now() + timezone.timedelta(days=100)
        committee = Committee.objects.create(paper=self.paper, editor=self.editor, deadline=custom_deadline)
        self.assertEqual(committee.deadline, custom_deadline)

    def test_saving_existing_committee_does_not_reset_deadline(self):
        committee = Committee.objects.create(paper=self.paper, editor=self.editor)
        original_deadline = committee.deadline
        committee.status = 'approved'
        committee.save()
        committee.refresh_from_db()
        self.assertEqual(committee.deadline, original_deadline)

    def test_final_statuses_constant(self):
        self.assertEqual(Committee.FINAL_STATUSES, {'accepted', 'rejected', 'revision', 'expired'})
        self.assertNotIn('pending', Committee.FINAL_STATUSES)
        self.assertNotIn('approved', Committee.FINAL_STATUSES)


class CommitteeMemberModelTests(TestCase):
    def setUp(self):
        self.editor = make_user('editor@example.com', 'editor')
        self.author = make_user('author@example.com', 'author')
        self.reviewer = make_user('rev@example.com', 'reviewer')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
        )
        self.committee = Committee.objects.create(paper=self.paper, editor=self.editor)

    def test_duplicate_member_for_same_committee_and_user_rejected(self):
        CommitteeMember.objects.create(committee=self.committee, user=self.reviewer, role='primary')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CommitteeMember.objects.create(committee=self.committee, user=self.reviewer, role='substitute')

    def test_default_response_and_decision_are_pending(self):
        member = CommitteeMember.objects.create(committee=self.committee, user=self.reviewer, role='primary')
        self.assertEqual(member.response, 'pending')
        self.assertEqual(member.paper_decision, 'pending')
        self.assertIsNone(member.is_approved)
