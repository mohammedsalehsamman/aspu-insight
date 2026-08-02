from datetime import timedelta
from unittest import mock

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from committees.models import Committee
from notifications.models import Notification, NotificationDelivery
from notifications.services import NotificationService
from notifications.tasks import (
    check_committee_deadlines_approaching,
    push_ws_notification,
    send_email_notification,
)
from notifications.tests.helpers import make_paper, make_user


class SendEmailNotificationTaskTest(TestCase):

    def _make_delivery(self, **overrides):
        recipient = overrides.pop('recipient', None) or make_user()
        notification = Notification.objects.create(
            recipient=recipient,
            notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='عنوان', body='نص',
        )
        defaults = dict(
            notification=notification, channel=NotificationDelivery.Channel.EMAIL,
            rendered_subject='موضوع تجريبي', rendered_body='محتوى تجريبي',
            idempotency_key=f"{notification.id}:email", max_attempts=2,
        )
        defaults.update(overrides)
        return NotificationDelivery.objects.create(**defaults)

    def test_successful_send_marks_sent_and_records_outbox(self):
        recipient = make_user(email='recipient@example.com')
        delivery = self._make_delivery(recipient=recipient)

        send_email_notification.apply(args=[delivery.id])

        delivery.refresh_from_db()
        self.assertEqual(delivery.status, NotificationDelivery.Status.SENT)
        self.assertIsNotNone(delivery.sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'موضوع تجريبي')
        self.assertEqual(mail.outbox[0].to, ['recipient@example.com'])

    def test_already_sent_is_noop(self):
        delivery = self._make_delivery(status=NotificationDelivery.Status.SENT)

        send_email_notification.apply(args=[delivery.id])

        self.assertEqual(len(mail.outbox), 0)

    def test_missing_delivery_row_is_noop(self):
        send_email_notification.apply(args=[999999])
        self.assertEqual(len(mail.outbox), 0)

    def test_failure_increments_attempts_then_gives_up_after_max(self):
        delivery = self._make_delivery(max_attempts=2)

        with mock.patch('notifications.tasks.send_mail', side_effect=ValueError('smtp down')):
            with self.assertRaises(ValueError):
                send_email_notification.apply(args=[delivery.id]).get()
            delivery.refresh_from_db()
            self.assertEqual(delivery.attempt_count, 1)
            self.assertEqual(delivery.status, NotificationDelivery.Status.RETRYING)

            with self.assertRaises(ValueError):
                send_email_notification.apply(args=[delivery.id]).get()
            delivery.refresh_from_db()
            self.assertEqual(delivery.attempt_count, 2)
            self.assertEqual(delivery.status, NotificationDelivery.Status.GIVEN_UP)

        self.assertEqual(len(mail.outbox), 0)


class FullEmailDispatchTest(TestCase):
    """يثبّت أن NotificationService.create_notification يجدول send_email_notification.delay(...)
    وpush_ws_notification.delay(...) عبر transaction.on_commit، كل واحدة بالمعرّف الصحيح.

    لا نعتمد هنا على تنفيذ Celery الفعلي (eager) لأن .delay() يحاول الاتصال بالناقل
    المُعرَّف في CELERY_BROKER_URL بغض النظر عن override_settings على task_always_eager —
    إعداد Celery الفعلي مُحمَّل مسبقاً في aspu_insight/celery.py عند استيراد التطبيق، فمحاكاة
    .delay() هي الطريقة الموثوقة لاختبار "هل جُدولت المهمة بالمعرّف الصحيح" بمعزل عن الناقل.
    push_ws_notification.delay يُجدوَل دوماً بصرف النظر عن نوع الإشعار، فيُموَّه في كلا
    الاختبارين حتى في اختبار البريد وحده."""

    def test_create_notification_dispatches_email_on_commit(self):
        author = make_user(role='author')
        paper = make_paper(author=author)

        with mock.patch('notifications.tasks.push_ws_notification.delay'):
            with mock.patch('notifications.tasks.send_email_notification.delay') as mocked_delay:
                with self.captureOnCommitCallbacks(execute=True):
                    notification = NotificationService.create_notification(
                        recipient=author,
                        notification_type=Notification.NotificationType.PAPER_PUBLISHED,
                        target=paper, target_repr=paper.title,
                        context={'paper_title': paper.title},
                    )

        delivery = NotificationDelivery.objects.get(notification=notification)
        self.assertEqual(delivery.channel, NotificationDelivery.Channel.EMAIL)
        self.assertIn(paper.title, delivery.rendered_body)
        mocked_delay.assert_called_once_with(delivery.id)

    def test_create_notification_dispatches_ws_push_on_commit(self):
        """نفس السبب أعلاه بالضبط، لكن لـ push_ws_notification بدل send_email_notification —
        نوع بلا بريد افتراضياً (SYSTEM_ANNOUNCEMENT فيه email=True فعلاً، فنموّهه أيضاً)."""
        recipient = make_user()

        with mock.patch('notifications.tasks.send_email_notification.delay'):
            with mock.patch('notifications.tasks.push_ws_notification.delay') as mocked_delay:
                with self.captureOnCommitCallbacks(execute=True):
                    notification = NotificationService.create_notification(
                        recipient=recipient,
                        notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
                        context={'fallback_title': 'عنوان', 'fallback_body': 'نص'},
                    )

        mocked_delay.assert_called_once_with(notification.id)


class PushWsNotificationTaskTest(TestCase):
    """يختبر push_ws_notification بمعزل عن NotificationService — نفس نمط
    SendEmailNotificationTaskTest أعلاه (استدعاء المهمة عبر .apply() مباشرة)."""

    def test_pushes_notification_new_event_to_recipient_group(self):
        recipient = make_user()
        notification = Notification.objects.create(
            recipient=recipient,
            notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='عنوان', body='نص',
        )
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_add)(f"notifications_user_{recipient.pk}", 'test-channel')

        push_ws_notification.apply(args=[notification.id])

        event = async_to_sync(channel_layer.receive)('test-channel')
        self.assertEqual(event, {
            'type': 'notification.new',
            'notification_id': notification.id,
            'unread_count': 1,
        })

    def test_missing_notification_is_noop(self):
        push_ws_notification.apply(args=[999999])  # يجب ألا يرمي استثناء


class CheckCommitteeDeadlinesApproachingTaskTest(TestCase):

    def test_creates_notification_and_is_idempotent_same_day(self):
        editor = make_user(role='editor')
        paper = make_paper()
        Committee.objects.create(
            paper=paper, editor=editor, status='pending', blinding_type='single_blind',
            deadline=timezone.now() + timedelta(days=1),
        )

        check_committee_deadlines_approaching()
        self.assertEqual(
            Notification.objects.filter(
                recipient=editor,
                notification_type=Notification.NotificationType.COMMITTEE_DEADLINE_APPROACHING,
            ).count(),
            1,
        )

        check_committee_deadlines_approaching()  # نفس اليوم — يجب ألا يكرر
        self.assertEqual(
            Notification.objects.filter(
                recipient=editor,
                notification_type=Notification.NotificationType.COMMITTEE_DEADLINE_APPROACHING,
            ).count(),
            1,
        )

    def test_does_not_notify_committee_outside_window(self):
        editor = make_user(role='editor')
        paper = make_paper()
        Committee.objects.create(
            paper=paper, editor=editor, status='pending', blinding_type='single_blind',
            deadline=timezone.now() + timedelta(days=10),
        )

        check_committee_deadlines_approaching()

        self.assertEqual(Notification.objects.filter(recipient=editor).count(), 0)
