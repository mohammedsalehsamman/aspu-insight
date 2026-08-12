from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound

from committees.models import Committee, CommitteeMember
from committees.services import CommitteeService
from notifications.models import Notification
from research.models import ResearchPaper

User = get_user_model()


def make_user(email, role, **kwargs):
    return User.objects.create(email=email, full_name=email.split('@')[0], role=role, specialization='law', **kwargs)


class GetAvailableReviewersTests(TestCase):
    def setUp(self):
        self.editor = make_user('editor@example.com', 'editor')
        self.author = make_user('author@example.com', 'author')
        self.reviewer1 = make_user('rev1@example.com', 'reviewer')
        self.reviewer2 = make_user('rev2@example.com', 'reviewer')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
        )

    def test_non_editor_non_staff_denied(self):
        reader = make_user('reader@example.com', 'reader')
        with self.assertRaises(PermissionDenied):
            CommitteeService.get_available_reviewers(reader, self.paper.id)

    def test_staff_non_editor_allowed(self):
        staff = make_user('staff@example.com', 'author', is_staff=True)
        result = CommitteeService.get_available_reviewers(staff, self.paper.id)
        self.assertEqual(set(result), {self.reviewer1, self.reviewer2})

    def test_paper_not_found(self):
        with self.assertRaises(NotFound):
            CommitteeService.get_available_reviewers(self.editor, 99999)

    def test_excludes_paper_author_and_non_reviewers(self):
        reviewers = CommitteeService.get_available_reviewers(self.editor, self.paper.id)
        self.assertEqual(set(reviewers), {self.reviewer1, self.reviewer2})

    @patch('committees.services.AIReviewerMatcherService')
    def test_uses_ai_ranking_when_available(self, mock_ai):
        mock_ai.rank_reviewers_by_specialization.return_value = [self.reviewer2, self.reviewer1]
        result = CommitteeService.get_available_reviewers(self.editor, self.paper.id)
        self.assertEqual(result, [self.reviewer2, self.reviewer1])
        mock_ai.rank_reviewers_by_specialization.assert_called_once()

    @patch('committees.services.AIReviewerMatcherService')
    def test_falls_back_when_ai_ranking_empty(self, mock_ai):
        mock_ai.rank_reviewers_by_specialization.return_value = []
        result = CommitteeService.get_available_reviewers(self.editor, self.paper.id)
        self.assertEqual(set(result), {self.reviewer1, self.reviewer2})

    @patch('committees.services.AIReviewerMatcherService')
    def test_falls_back_when_ai_ranking_raises(self, mock_ai):
        mock_ai.rank_reviewers_by_specialization.side_effect = Exception('boom')
        result = CommitteeService.get_available_reviewers(self.editor, self.paper.id)
        self.assertEqual(set(result), {self.reviewer1, self.reviewer2})

    @patch('committees.services.AIReviewerMatcherService', None)
    def test_no_ai_matcher_uses_plain_list(self):
        result = CommitteeService.get_available_reviewers(self.editor, self.paper.id)
        self.assertEqual(set(result), {self.reviewer1, self.reviewer2})


class CreateCommitteeTests(TestCase):
    def setUp(self):
        self.editor = make_user('editor@example.com', 'editor')
        self.author = make_user('author@example.com', 'author')
        self.reviewers = [make_user(f'rev{i}@example.com', 'reviewer') for i in range(5)]
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
        )
        self.primary_ids = [r.user_id for r in self.reviewers[:3]]
        self.substitute_ids = [r.user_id for r in self.reviewers[3:5]]

    def test_non_editor_denied(self):
        with self.assertRaises(PermissionDenied):
            CommitteeService.create_committee(self.author, self.paper.id, self.primary_ids, self.substitute_ids, 'single_blind')

    def test_paper_not_found(self):
        with self.assertRaises(NotFound):
            CommitteeService.create_committee(self.editor, 99999, self.primary_ids, self.substitute_ids, 'single_blind')

    def test_happy_path_creates_committee_and_members(self):
        committee = CommitteeService.create_committee(
            self.editor, self.paper.id, self.primary_ids, self.substitute_ids, 'double_blind'
        )
        self.assertEqual(committee.paper, self.paper)
        self.assertEqual(committee.editor_id, self.editor.user_id)
        self.assertEqual(committee.blinding_type, 'double_blind')
        self.assertEqual(committee.status, 'pending')
        self.assertIsNotNone(committee.deadline)

        members = CommitteeMember.objects.filter(committee=committee)
        self.assertEqual(members.count(), 5)
        primaries = members.filter(role='primary')
        substitutes = members.filter(role='substitute')
        self.assertEqual(primaries.count(), 3)
        self.assertEqual(substitutes.count(), 2)
        self.assertTrue(all(not m.is_substitute for m in primaries))
        self.assertTrue(all(m.is_substitute for m in substitutes))

    def test_existing_non_expired_committee_raises(self):
        CommitteeService.create_committee(self.editor, self.paper.id, self.primary_ids, self.substitute_ids, 'single_blind')
        with self.assertRaises(ValidationError):
            CommitteeService.create_committee(self.editor, self.paper.id, self.primary_ids, self.substitute_ids, 'single_blind')

    def test_existing_expired_committee_is_replaced(self):
        old = CommitteeService.create_committee(self.editor, self.paper.id, self.primary_ids, self.substitute_ids, 'single_blind')
        old.status = 'expired'
        old.save()

        new_committee = CommitteeService.create_committee(
            self.editor, self.paper.id, self.primary_ids, self.substitute_ids, 'single_blind'
        )
        self.assertNotEqual(old.pk, new_committee.pk)
        self.assertEqual(Committee.objects.filter(paper=self.paper).count(), 1)

    def test_wrong_primary_count_raises(self):
        with self.assertRaises(ValidationError):
            CommitteeService.create_committee(
                self.editor, self.paper.id, self.primary_ids[:2], self.substitute_ids, 'single_blind'
            )

    def test_duplicate_primary_ids_raises(self):
        dup = [self.primary_ids[0], self.primary_ids[0], self.primary_ids[1]]
        with self.assertRaises(ValidationError):
            CommitteeService.create_committee(self.editor, self.paper.id, dup, self.substitute_ids, 'single_blind')

    def test_duplicate_substitute_ids_raises(self):
        dup_subs = [self.substitute_ids[0], self.substitute_ids[0]]
        with self.assertRaises(ValidationError):
            CommitteeService.create_committee(self.editor, self.paper.id, self.primary_ids, dup_subs, 'single_blind')

    def test_nonexistent_user_id_raises(self):
        bad_ids = self.primary_ids[:2] + [999999]
        with self.assertRaises(ValidationError):
            CommitteeService.create_committee(self.editor, self.paper.id, bad_ids, self.substitute_ids, 'single_blind')

    def test_non_reviewer_role_raises(self):
        non_reviewer = make_user('notrev@example.com', 'author')
        bad_ids = self.primary_ids[:2] + [non_reviewer.user_id]
        with self.assertRaises(ValidationError):
            CommitteeService.create_committee(self.editor, self.paper.id, bad_ids, self.substitute_ids, 'single_blind')

    def test_staff_non_editor_allowed(self):
        staff = make_user('staff@example.com', 'author', is_staff=True)
        committee = CommitteeService.create_committee(
            staff, self.paper.id, self.primary_ids, self.substitute_ids, 'single_blind'
        )
        self.assertIsNotNone(committee.pk)


class HandleReviewerResponseTests(TestCase):
    def setUp(self):
        self.editor = make_user('editor@example.com', 'editor')
        self.author = make_user('author@example.com', 'author')
        self.reviewers = [make_user(f'rev{i}@example.com', 'reviewer') for i in range(5)]
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
        )
        self.committee = Committee.objects.create(paper=self.paper, editor=self.editor, status='pending')
        self.primary_members = [
            CommitteeMember.objects.create(committee=self.committee, user=r, role='primary', is_substitute=False)
            for r in self.reviewers[:3]
        ]
        self.substitute_member = CommitteeMember.objects.create(
            committee=self.committee, user=self.reviewers[3], role='substitute', is_substitute=True
        )

    def test_non_reviewer_denied(self):
        with self.assertRaises(PermissionDenied):
            CommitteeService.handle_reviewer_response(self.editor, self.primary_members[0].id, True)

    def test_member_not_found_for_wrong_user(self):
        with self.assertRaises(NotFound):
            CommitteeService.handle_reviewer_response(self.reviewers[4], self.primary_members[0].id, True)

    def test_final_status_committee_raises(self):
        self.committee.status = 'accepted'
        self.committee.save()
        with self.assertRaises(ValidationError):
            CommitteeService.handle_reviewer_response(self.reviewers[0], self.primary_members[0].id, True)

    def test_repeating_same_response_raises(self):
        CommitteeService.handle_reviewer_response(self.reviewers[0], self.primary_members[0].id, True)
        with self.assertRaises(ValidationError):
            CommitteeService.handle_reviewer_response(self.reviewers[0], self.primary_members[0].id, True)

    def test_third_acceptance_marks_committee_approved(self):
        CommitteeService.handle_reviewer_response(self.reviewers[0], self.primary_members[0].id, True)
        CommitteeService.handle_reviewer_response(self.reviewers[1], self.primary_members[1].id, True)
        self.committee.refresh_from_db()
        self.assertEqual(self.committee.status, 'pending')

        CommitteeService.handle_reviewer_response(self.reviewers[2], self.primary_members[2].id, True)
        self.committee.refresh_from_db()
        self.assertEqual(self.committee.status, 'approved')

    def test_substitute_promoted_to_primary_on_acceptance(self):
        CommitteeService.handle_reviewer_response(self.reviewers[3], self.substitute_member.id, True)
        self.substitute_member.refresh_from_db()
        self.assertFalse(self.substitute_member.is_substitute)
        self.assertEqual(self.substitute_member.role, 'primary')
        self.assertEqual(self.substitute_member.response, 'accepted')

    @patch('committees.services.NotificationService.create_notification')
    def test_decline_after_acceptance_resets_committee_and_invites_substitute(self, mock_notify):
        CommitteeService.handle_reviewer_response(self.reviewers[0], self.primary_members[0].id, True)
        CommitteeService.handle_reviewer_response(self.reviewers[1], self.primary_members[1].id, True)
        CommitteeService.handle_reviewer_response(self.reviewers[2], self.primary_members[2].id, True)
        self.committee.refresh_from_db()
        self.assertEqual(self.committee.status, 'approved')

        CommitteeService.handle_reviewer_response(self.reviewers[0], self.primary_members[0].id, False)

        self.committee.refresh_from_db()
        self.primary_members[0].refresh_from_db()
        self.assertEqual(self.committee.status, 'pending')
        self.assertEqual(self.primary_members[0].response, 'declined')
        self.assertEqual(self.primary_members[0].paper_decision, 'pending')
        mock_notify.assert_called_once()
        self.assertEqual(mock_notify.call_args.kwargs['recipient'], self.substitute_member.user)
        self.assertEqual(
            mock_notify.call_args.kwargs['notification_type'],
            Notification.NotificationType.REVIEWER_ASSIGNED_TO_COMMITTEE,
        )

    @patch('committees.services.NotificationService.create_notification')
    def test_decline_without_prior_acceptance_does_not_invite_substitute(self, mock_notify):
        CommitteeService.handle_reviewer_response(self.reviewers[0], self.primary_members[0].id, False)
        mock_notify.assert_not_called()
        self.primary_members[0].refresh_from_db()
        self.assertEqual(self.primary_members[0].response, 'declined')


class GetCommitteeInvitationTests(TestCase):
    def setUp(self):
        self.editor = make_user('editor@example.com', 'editor')
        self.author = make_user('author@example.com', 'author')
        self.reviewer = make_user('rev@example.com', 'reviewer')
        self.other_reviewer = make_user('other-rev@example.com', 'reviewer')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
        )
        self.committee = Committee.objects.create(paper=self.paper, editor=self.editor, status='pending')
        self.member = CommitteeMember.objects.create(committee=self.committee, user=self.reviewer, role='primary')

    def test_non_reviewer_denied(self):
        with self.assertRaises(PermissionDenied):
            CommitteeService.get_committee_invitation(self.editor, self.member.id)

    def test_member_not_found_for_wrong_user(self):
        with self.assertRaises(NotFound):
            CommitteeService.get_committee_invitation(self.other_reviewer, self.member.id)

    def test_returns_member_with_related_committee_and_paper(self):
        member = CommitteeService.get_committee_invitation(self.reviewer, self.member.id)
        self.assertEqual(member.committee_id, self.committee.id)
        self.assertEqual(member.committee.paper.title, self.paper.title)
        self.assertEqual(member.committee.paper.abstract, self.paper.abstract)


class GetMyInvitationsTests(TestCase):
    def setUp(self):
        self.editor = make_user('editor@example.com', 'editor')
        self.author = make_user('author@example.com', 'author')
        self.reviewer = make_user('rev@example.com', 'reviewer')
        self.other_reviewer = make_user('other-rev@example.com', 'reviewer')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
        )
        self.committee = Committee.objects.create(paper=self.paper, editor=self.editor, status='pending')

    def test_non_reviewer_denied(self):
        with self.assertRaises(PermissionDenied):
            CommitteeService.get_my_invitations(self.editor)

    def test_returns_only_current_users_memberships(self):
        my_member = CommitteeMember.objects.create(committee=self.committee, user=self.reviewer, role='primary')
        CommitteeMember.objects.create(committee=self.committee, user=self.other_reviewer, role='substitute')

        result = CommitteeService.get_my_invitations(self.reviewer)

        self.assertEqual(list(result), [my_member])

    def test_empty_for_reviewer_with_no_memberships(self):
        result = CommitteeService.get_my_invitations(self.reviewer)
        self.assertEqual(result.count(), 0)

    def test_ordered_by_most_recent_first(self):
        older = CommitteeMember.objects.create(committee=self.committee, user=self.reviewer, role='primary')

        other_paper = ResearchPaper.objects.create(
            title='Paper 2', abstract='abstract', author=self.author, specialization='law',
        )
        other_committee = Committee.objects.create(paper=other_paper, editor=self.editor, status='pending')
        newer = CommitteeMember.objects.create(committee=other_committee, user=self.reviewer, role='primary')

        CommitteeMember.objects.filter(pk=older.pk).update(assigned_at=timezone.now() - timedelta(days=1))

        result = list(CommitteeService.get_my_invitations(self.reviewer))
        self.assertEqual(result, [newer, older])


class SubmitReviewDecisionTests(TestCase):
    def setUp(self):
        self.editor = make_user('editor@example.com', 'editor')
        self.author = make_user('author@example.com', 'author')
        self.reviewers = [make_user(f'rev{i}@example.com', 'reviewer') for i in range(3)]
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
        )
        self.committee = Committee.objects.create(paper=self.paper, editor=self.editor, status='approved')
        self.members = [
            CommitteeMember.objects.create(committee=self.committee, user=r, role='primary', is_substitute=False)
            for r in self.reviewers
        ]

    def test_non_reviewer_denied(self):
        with self.assertRaises(PermissionDenied):
            CommitteeService.submit_review_decision(self.editor, self.members[0].id, 'accept_paper', '')

    def test_member_not_found(self):
        outsider = make_user('outsider@example.com', 'reviewer')
        with self.assertRaises(NotFound):
            CommitteeService.submit_review_decision(outsider, self.members[0].id, 'accept_paper', '')

    def test_committee_not_approved_raises(self):
        self.committee.status = 'pending'
        self.committee.save()
        with self.assertRaises(ValidationError):
            CommitteeService.submit_review_decision(self.reviewers[0], self.members[0].id, 'accept_paper', '')

    def test_invalid_decision_raises(self):
        with self.assertRaises(ValidationError):
            CommitteeService.submit_review_decision(self.reviewers[0], self.members[0].id, 'bogus', '')

    def test_partial_votes_do_not_change_committee_status(self):
        CommitteeService.submit_review_decision(self.reviewers[0], self.members[0].id, 'accept_paper', 'ok')
        self.committee.refresh_from_db()
        self.assertEqual(self.committee.status, 'approved')

    def test_two_accepts_moves_to_accepted(self):
        CommitteeService.submit_review_decision(self.reviewers[0], self.members[0].id, 'accept_paper', '')
        CommitteeService.submit_review_decision(self.reviewers[1], self.members[1].id, 'accept_paper', '')
        CommitteeService.submit_review_decision(self.reviewers[2], self.members[2].id, 'reject_paper', '')
        self.committee.refresh_from_db()
        self.assertEqual(self.committee.status, 'accepted')

    def test_two_rejects_moves_to_rejected(self):
        CommitteeService.submit_review_decision(self.reviewers[0], self.members[0].id, 'reject_paper', '')
        CommitteeService.submit_review_decision(self.reviewers[1], self.members[1].id, 'reject_paper', '')
        CommitteeService.submit_review_decision(self.reviewers[2], self.members[2].id, 'accept_paper', '')
        self.committee.refresh_from_db()
        self.assertEqual(self.committee.status, 'rejected')

    def test_split_decision_moves_to_revision(self):
        CommitteeService.submit_review_decision(self.reviewers[0], self.members[0].id, 'accept_paper', '')
        CommitteeService.submit_review_decision(self.reviewers[1], self.members[1].id, 'reject_paper', '')
        CommitteeService.submit_review_decision(self.reviewers[2], self.members[2].id, 'modify_paper', '')
        self.committee.refresh_from_db()
        self.assertEqual(self.committee.status, 'revision')

    def test_comment_saved_on_member(self):
        CommitteeService.submit_review_decision(self.reviewers[0], self.members[0].id, 'modify_paper', 'please fix intro')
        self.members[0].refresh_from_db()
        self.assertEqual(self.members[0].comments, 'please fix intro')


class TryForceDecisionTests(TestCase):
    def setUp(self):
        self.editor = make_user('editor@example.com', 'editor')
        self.author = make_user('author@example.com', 'author')
        self.reviewers = [make_user(f'rev{i}@example.com', 'reviewer') for i in range(3)]
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
        )
        self.committee = Committee.objects.create(paper=self.paper, editor=self.editor, status='approved')

    def _create_members(self, decisions):
        return [
            CommitteeMember.objects.create(
                committee=self.committee, user=r, role='primary', is_substitute=False, paper_decision=d
            )
            for r, d in zip(self.reviewers, decisions)
        ]

    def test_two_accepts_forces_accepted(self):
        self._create_members(['accept_paper', 'accept_paper', 'pending'])
        result = CommitteeService._try_force_decision(self.committee)
        self.assertTrue(result)
        self.committee.refresh_from_db()
        self.assertEqual(self.committee.status, 'accepted')

    def test_two_rejects_forces_rejected(self):
        self._create_members(['reject_paper', 'reject_paper', 'pending'])
        result = CommitteeService._try_force_decision(self.committee)
        self.assertTrue(result)
        self.committee.refresh_from_db()
        self.assertEqual(self.committee.status, 'rejected')

    def test_two_modifies_forces_revision(self):
        self._create_members(['modify_paper', 'modify_paper', 'pending'])
        result = CommitteeService._try_force_decision(self.committee)
        self.assertTrue(result)
        self.committee.refresh_from_db()
        self.assertEqual(self.committee.status, 'revision')

    def test_no_majority_returns_false(self):
        self._create_members(['accept_paper', 'reject_paper', 'pending'])
        result = CommitteeService._try_force_decision(self.committee)
        self.assertFalse(result)
        self.committee.refresh_from_db()
        self.assertEqual(self.committee.status, 'approved')


class ExpireOverdueCommitteesTests(TestCase):
    def setUp(self):
        self.editor = make_user('editor@example.com', 'editor')
        self.author = make_user('author@example.com', 'author')
        self.reviewers = [make_user(f'rev{i}@example.com', 'reviewer') for i in range(3)]
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
        )

    def _make_overdue_committee(self, status='pending'):
        committee = Committee.objects.create(paper=self.paper, editor=self.editor, status=status)
        Committee.objects.filter(pk=committee.pk).update(deadline=timezone.now() - timedelta(days=1))
        committee.refresh_from_db()
        return committee

    @patch('committees.services.NotificationService.create_notification')
    def test_overdue_without_majority_expires_and_emails(self, mock_notify):
        committee = self._make_overdue_committee('pending')
        CommitteeService.expire_overdue_committees()
        committee.refresh_from_db()
        self.assertEqual(committee.status, 'expired')
        mock_notify.assert_called_once()
        self.assertEqual(mock_notify.call_args.kwargs['recipient'], self.editor)
        self.assertEqual(
            mock_notify.call_args.kwargs['notification_type'],
            Notification.NotificationType.COMMITTEE_DEADLINE_EXPIRED,
        )

    @patch('committees.services.NotificationService.create_notification')
    def test_overdue_with_majority_forces_decision_instead_of_expiring(self, mock_notify):
        committee = self._make_overdue_committee('approved')
        for r, d in zip(self.reviewers, ['accept_paper', 'accept_paper', 'pending']):
            CommitteeMember.objects.create(
                committee=committee, user=r, role='primary', is_substitute=False, paper_decision=d
            )
        CommitteeService.expire_overdue_committees()
        committee.refresh_from_db()
        self.assertEqual(committee.status, 'accepted')
        # _try_force_decision notifies the decision instead (COMMITTEE_REVIEW_RECEIVED),
        # so the expiry-specific notification must never fire.
        for call in mock_notify.call_args_list:
            self.assertNotEqual(
                call.kwargs['notification_type'],
                Notification.NotificationType.COMMITTEE_DEADLINE_EXPIRED,
            )

    @patch('committees.services.NotificationService.create_notification')
    def test_not_overdue_committee_is_untouched(self, mock_notify):
        committee = Committee.objects.create(paper=self.paper, editor=self.editor, status='pending')
        CommitteeService.expire_overdue_committees()
        committee.refresh_from_db()
        self.assertEqual(committee.status, 'pending')
        mock_notify.assert_not_called()

    @patch('committees.services.NotificationService.create_notification')
    def test_final_status_committee_not_touched_even_if_overdue(self, mock_notify):
        committee = self._make_overdue_committee('rejected')
        CommitteeService.expire_overdue_committees()
        committee.refresh_from_db()
        self.assertEqual(committee.status, 'rejected')
        mock_notify.assert_not_called()


class GetResearchPaperDetailsTests(TestCase):
    def setUp(self):
        self.author = make_user('author@example.com', 'author')
        self.editor = make_user('editor@example.com', 'editor')
        self.reviewer = make_user('reviewer@example.com', 'reviewer')
        self.paper = ResearchPaper.objects.create(
            title='Paper', abstract='abstract', author=self.author, specialization='law',
        )

    def test_paper_not_found_raises(self):
        with self.assertRaises(NotFound):
            CommitteeService.get_research_paper_details(self.editor, 99999)

    @patch('configuration.security.can_user_access_pdf', return_value=True)
    def test_author_sees_own_name_and_pdf(self, mock_access):
        data, is_blinded = CommitteeService.get_research_paper_details(self.author, self.paper.id)
        self.assertFalse(is_blinded)
        self.assertEqual(data['author_name'], str(self.author))
        self.assertIn(self.author.email, data['author_name'])
        self.assertEqual(data['id'], self.paper.id)

    @patch('configuration.security.can_user_access_pdf', return_value=False)
    def test_reviewer_sees_anonymous_author_when_blinded(self, mock_access):
        committee = Committee.objects.create(paper=self.paper, editor=self.editor, status='pending')
        CommitteeMember.objects.create(committee=committee, user=self.reviewer, role='primary', is_substitute=False)
        data, is_blinded = CommitteeService.get_research_paper_details(self.reviewer, self.paper.id)
        self.assertTrue(is_blinded)
        self.assertEqual(data['author_name'], 'Anonymous Author (Hidden for Committee Review)')
        self.assertIsNone(data['pdf_file'])

    @patch('configuration.security.can_user_access_pdf', return_value=False)
    def test_editor_still_sees_author_name_even_when_blinded(self, mock_access):
        self.paper.assigned_editor = self.editor
        self.paper.save(update_fields=['assigned_editor'])
        data, is_blinded = CommitteeService.get_research_paper_details(self.editor, self.paper.id)
        self.assertTrue(is_blinded)
        self.assertEqual(data['author_name'], str(self.author))
