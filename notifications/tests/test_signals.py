from datetime import timedelta

from django.core import mail
from django.urls import reverse
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.serializers import UserUpdateSerializer
from assistantReview.models import AssistantReview
from assistantReview.services import AssistantReviewService
from committees.models import Committee, CommitteeMember
from committees.services import CommitteeService
from notifications.models import Notification
from notifications.tests.helpers import make_paper, make_user
from research.models import ResearchPaper
from researchHistory.models import ResearchHistory


class ResearchHistorySignalTest(TestCase):
    """يثبّت الربط الفعلي عبر ResearchHistory.post_save، لا الخدمة المعزولة فقط."""

    def test_assistant_review_reject_notifies_author(self):
        author = make_user(role='author')
        assistant = make_user(role='assistant_editor')
        paper = make_paper(author=author, status=ResearchPaper.Status.SUBMITTED)

        AssistantReviewService.create_review(paper, assistant, {
            'decision': AssistantReview.Decision.REJECT,
            'notes': 'يحتاج تعديلات',
        })

        self.assertEqual(ResearchHistory.objects.filter(paper=paper).count(), 1)
        notification = Notification.objects.get(recipient=author)
        self.assertEqual(
            notification.notification_type, Notification.NotificationType.ASSISTANT_REVIEW_RECEIVED,
        )

    def test_resaving_same_history_row_does_not_duplicate_notification(self):
        """حارس انحدار: التكرار مستحيل لأن created=True مطلوب — لو انكسر هذا مستقبلاً
        (خطأ افتراضي: إعادة حفظ سجل موجود) لن يُنشأ إشعار إضافي."""
        author = make_user(role='author')
        paper = make_paper(author=author, status=ResearchPaper.Status.SUBMITTED)
        history = ResearchHistory.objects.create(
            paper=paper, from_status='submitted', to_status='editor_review',
        )
        self.assertEqual(Notification.objects.filter(recipient=author).count(), 1)

        history.note = 'تعديل لاحق على نفس السجل'
        history.save()  # created=False هذه المرة

        self.assertEqual(Notification.objects.filter(recipient=author).count(), 1)

    def test_transient_status_does_not_notify(self):
        author = make_user(role='author')
        paper = make_paper(author=author, status=ResearchPaper.Status.PENDING)
        ResearchHistory.objects.create(
            paper=paper, from_status='pending', to_status='checking_plagiarism',
        )
        self.assertEqual(Notification.objects.filter(recipient=author).count(), 0)


class AdminAssignEditorViewTest(TestCase):

    def test_assigning_editor_notifies_editor(self):
        admin = make_user(role='admin')
        editor = make_user(role='editor')
        paper = make_paper()

        client = APIClient()
        client.force_authenticate(user=admin)
        url = reverse('admin-dashboard-assign-editor', args=[paper.pk])
        response = client.patch(url, {'editor_id': editor.user_id}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification = Notification.objects.get(recipient=editor)
        self.assertEqual(notification.notification_type, Notification.NotificationType.EDITOR_ASSIGNED)


class CommitteeCreationTest(TestCase):

    def test_create_committee_notifies_all_members(self):
        editor = make_user(role='editor')
        paper = make_paper()
        primaries = [make_user(role='reviewer') for _ in range(3)]
        substitute = make_user(role='reviewer')

        committee = CommitteeService.create_committee(
            user=editor,
            paper_id=paper.id,
            primary_ids=[u.user_id for u in primaries],
            substitute_ids=[substitute.user_id],
            blinding_type='single_blind',
        )

        for reviewer in primaries + [substitute]:
            notification = Notification.objects.get(
                recipient=reviewer, notification_type=Notification.NotificationType.REVIEWER_ASSIGNED_TO_COMMITTEE,
            )
            self.assertEqual(notification.target_object_id, committee.id)


class RoleChangeSignalTest(TestCase):

    def test_role_change_notifies_user(self):
        user = make_user(role='author')
        user.role = 'reviewer'
        user.save()

        notification = Notification.objects.get(recipient=user)
        self.assertEqual(notification.notification_type, Notification.NotificationType.ROLE_CHANGED)
        self.assertEqual(notification.data['old_role'], 'author')
        self.assertEqual(notification.data['new_role'], 'reviewer')

    def test_no_op_save_does_not_notify(self):
        user = make_user(role='author')
        user.full_name = 'اسم محدَّث'
        user.save()  # لم يتغيّر role

        self.assertEqual(Notification.objects.filter(recipient=user).count(), 0)

    def test_serializer_update_path_also_triggers_signal(self):
        """يثبّت أن التغيير عبر UserUpdateSerializer (مسار AdminUserDetailView الفعلي) يُطلق الإشارة أيضاً،
        لا فقط user.save() المباشر في الاختبارات."""
        user = make_user(role='author')
        serializer = UserUpdateSerializer(instance=user, data={'role': 'editor'}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        notification = Notification.objects.get(recipient=user)
        self.assertEqual(notification.notification_type, Notification.NotificationType.ROLE_CHANGED)


class CommitteeReviewDecisionTest(TestCase):
    """يثبّت الربط الفعلي في CommitteeService.submit_review_decision (Phase 2)."""

    def test_notification_fires_only_once_all_members_voted(self):
        editor = make_user(role='editor')
        author = make_user(role='author')
        paper = make_paper(author=author)
        committee = Committee.objects.create(
            paper=paper, editor=editor, status='approved', blinding_type='single_blind',
        )
        reviewers = [make_user(role='reviewer') for _ in range(3)]
        members = [
            CommitteeMember.objects.create(
                committee=committee, user=r, role='primary', is_substitute=False, is_approved=True,
            )
            for r in reviewers
        ]

        CommitteeService.submit_review_decision(reviewers[0], members[0].id, 'accept_paper', '')
        self.assertEqual(Notification.objects.filter(recipient__in=[author, editor]).count(), 0)

        CommitteeService.submit_review_decision(reviewers[1], members[1].id, 'accept_paper', '')
        self.assertEqual(Notification.objects.filter(recipient__in=[author, editor]).count(), 0)

        CommitteeService.submit_review_decision(reviewers[2], members[2].id, 'reject_paper', '')
        committee.refresh_from_db()
        self.assertEqual(committee.status, 'accepted')
        for recipient in (author, editor):
            notification = Notification.objects.get(
                recipient=recipient, notification_type=Notification.NotificationType.COMMITTEE_REVIEW_RECEIVED,
            )
            self.assertEqual(notification.target_object_id, committee.id)


class CommitteeExpirySignalTest(TestCase):
    """يثبّت أن انتهاء مهلة اللجنة يُشعِر المحرر عبر النظام الموحّد، لا البريد اليدوي القديم (محذوف)."""

    def test_expired_committee_notifies_editor(self):
        editor = make_user(role='editor')
        paper = make_paper()
        committee = Committee.objects.create(
            paper=paper, editor=editor, status='pending', blinding_type='single_blind',
            deadline=timezone.now() - timedelta(days=1),
        )

        CommitteeService.expire_overdue_committees()

        committee.refresh_from_db()
        self.assertEqual(committee.status, 'expired')
        notification = Notification.objects.get(
            recipient=editor, notification_type=Notification.NotificationType.COMMITTEE_DEADLINE_EXPIRED,
        )
        self.assertEqual(notification.target_object_id, committee.id)
        # الإرسال الفعلي عبر Celery مؤجَّل لـ transaction.on_commit ولا يُنفَّذ داخل TestCase
        self.assertEqual(len(mail.outbox), 0)


class SubstituteInvitationSignalTest(TestCase):
    """يثبّت أن اعتذار عضو أساسي يُشعِر البديل عبر النظام الموحّد، لا البريد اليدوي القديم (محذوف)."""

    def test_declining_member_notifies_substitute(self):
        editor = make_user(role='editor')
        paper = make_paper()
        committee = Committee.objects.create(
            paper=paper, editor=editor, status='pending', blinding_type='single_blind',
        )
        primary_reviewer = make_user(role='reviewer')
        substitute_reviewer = make_user(role='reviewer')
        primary_member = CommitteeMember.objects.create(
            committee=committee, user=primary_reviewer, role='primary', is_substitute=False, is_approved=True,
        )
        CommitteeMember.objects.create(
            committee=committee, user=substitute_reviewer, role='substitute', is_substitute=True, is_approved=None,
        )

        CommitteeService.handle_reviewer_response(primary_reviewer, primary_member.id, False)

        notification = Notification.objects.get(
            recipient=substitute_reviewer,
            notification_type=Notification.NotificationType.REVIEWER_ASSIGNED_TO_COMMITTEE,
        )
        self.assertEqual(notification.target_object_id, committee.id)
