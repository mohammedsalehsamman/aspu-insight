from datetime import timedelta
from unittest import mock

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from firebase_admin.messaging import UnregisteredError

from committees.models import Committee
from notifications.models import DeviceToken, Notification, NotificationDelivery, UserNotificationPreference
from notifications.services import NotificationService
from notifications.tasks import (
    check_committee_deadlines_approaching,
    cleanup_old_read_notifications,
    push_ws_notification,
    send_daily_notification_digest,
    send_email_notification,
    send_push_notification,
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


class FullPushDispatchTest(TestCase):
    """push مُعطَّل افتراضياً لكل الأنواع (لا تطبيق جوال بعد) — نفعّله صراحة عبر
    UserNotificationPreference لإثبات أن create_notification ينشئ NotificationDelivery(PUSH)
    لكل جهاز نشط فقط (لا الأجهزة المعطَّلة) ويجدول send_push_notification.delay بالمعرّف الصحيح."""

    def test_create_notification_dispatches_push_per_active_device_only(self):
        recipient = make_user()
        UserNotificationPreference.objects.create(
            user=recipient, notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            in_app_enabled=True, email_enabled=False, push_enabled=True,
        )
        active_device = DeviceToken.objects.create(user=recipient, token='active-1', platform='android')
        DeviceToken.objects.create(user=recipient, token='inactive-1', platform='ios', is_active=False)

        with mock.patch('notifications.tasks.push_ws_notification.delay'):
            with mock.patch('notifications.tasks.send_push_notification.delay') as mocked_delay:
                with self.captureOnCommitCallbacks(execute=True):
                    notification = NotificationService.create_notification(
                        recipient=recipient,
                        notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
                        context={'fallback_title': 'عنوان', 'fallback_body': 'نص'},
                    )

        deliveries = NotificationDelivery.objects.filter(
            notification=notification, channel=NotificationDelivery.Channel.PUSH,
        )
        self.assertEqual(deliveries.count(), 1)
        self.assertEqual(deliveries.first().device_token, active_device)
        mocked_delay.assert_called_once_with(deliveries.first().id)


class SendPushNotificationTaskTest(TestCase):
    """يختبر send_push_notification بمعزل عن NotificationService — محاكاة استدعاء FCM فقط،
    فلا تطبيق جوال فعلي موجود لاختبار طرف-إلى-طرف (راجع خطة الإشعارات، المرحلة 5)."""

    def _make_delivery(self, **overrides):
        recipient = overrides.pop('recipient', None) or make_user()
        device_token = overrides.pop('device_token', None) or DeviceToken.objects.create(
            user=recipient, token=f"tok-{recipient.pk}", platform='android',
        )
        notification = Notification.objects.create(
            recipient=recipient, notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='عنوان', body='نص',
        )
        defaults = dict(
            notification=notification, channel=NotificationDelivery.Channel.PUSH, device_token=device_token,
            rendered_subject='عنوان push', rendered_body='نص push',
            idempotency_key=f"{notification.id}:push:{device_token.id}", max_attempts=2,
        )
        defaults.update(overrides)
        return NotificationDelivery.objects.create(**defaults)

    def test_without_firebase_credentials_gives_up_immediately(self):
        delivery = self._make_delivery()

        with mock.patch('firebase_admin.messaging.send') as mocked_send:
            send_push_notification.apply(args=[delivery.id])

        mocked_send.assert_not_called()
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, NotificationDelivery.Status.GIVEN_UP)
        self.assertIn('FIREBASE_CREDENTIALS_PATH', delivery.error_message)

    def test_missing_delivery_row_is_noop(self):
        send_push_notification.apply(args=[999999])  # يجب ألا يرمي استثناء

    def test_already_sent_is_noop(self):
        delivery = self._make_delivery(status=NotificationDelivery.Status.SENT)

        with mock.patch('firebase_admin.messaging.send') as mocked_send:
            send_push_notification.apply(args=[delivery.id])

        mocked_send.assert_not_called()

    @override_settings(FIREBASE_CREDENTIALS_PATH='/fake/service-account.json')
    def test_successful_send_marks_sent(self):
        delivery = self._make_delivery()

        with mock.patch('notifications.tasks._get_firebase_app'):
            with mock.patch('firebase_admin.messaging.send', return_value='projects/x/messages/1') as mocked_send:
                send_push_notification.apply(args=[delivery.id])

        delivery.refresh_from_db()
        self.assertEqual(delivery.status, NotificationDelivery.Status.SENT)
        self.assertEqual(delivery.provider_message_id, 'projects/x/messages/1')
        self.assertIsNotNone(delivery.sent_at)
        mocked_send.assert_called_once()

    @override_settings(FIREBASE_CREDENTIALS_PATH='/fake/service-account.json')
    def test_unregistered_token_deactivates_device_and_gives_up(self):
        delivery = self._make_delivery()

        with mock.patch('notifications.tasks._get_firebase_app'):
            with mock.patch('firebase_admin.messaging.send', side_effect=UnregisteredError('gone')):
                send_push_notification.apply(args=[delivery.id])

        delivery.refresh_from_db()
        delivery.device_token.refresh_from_db()
        self.assertEqual(delivery.status, NotificationDelivery.Status.GIVEN_UP)
        self.assertFalse(delivery.device_token.is_active)

    @override_settings(FIREBASE_CREDENTIALS_PATH='/fake/service-account.json')
    def test_transient_failure_increments_attempts_then_gives_up_after_max(self):
        delivery = self._make_delivery(max_attempts=2)

        with mock.patch('notifications.tasks._get_firebase_app'):
            with mock.patch('firebase_admin.messaging.send', side_effect=ValueError('network down')):
                with self.assertRaises(ValueError):
                    send_push_notification.apply(args=[delivery.id]).get()
                delivery.refresh_from_db()
                self.assertEqual(delivery.attempt_count, 1)
                self.assertEqual(delivery.status, NotificationDelivery.Status.RETRYING)

                with self.assertRaises(ValueError):
                    send_push_notification.apply(args=[delivery.id]).get()
                delivery.refresh_from_db()
                self.assertEqual(delivery.attempt_count, 2)
                self.assertEqual(delivery.status, NotificationDelivery.Status.GIVEN_UP)


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


class SendDailyNotificationDigestTaskTest(TestCase):
    """لا يمرّ عبر NotificationDelivery — بريد ملخّص مباشر (send_mail)، راجع docstring المهمة."""

    def test_sends_one_email_per_user_with_unread_notifications(self):
        user = make_user(email='digest@example.com')
        Notification.objects.create(
            recipient=user, notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='إشعار 1', body='نص',
        )
        Notification.objects.create(
            recipient=user, notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='إشعار 2', body='نص',
        )

        sent = send_daily_notification_digest()

        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['digest@example.com'])
        self.assertIn('إشعار 1', mail.outbox[0].body)
        self.assertIn('إشعار 2', mail.outbox[0].body)

    def test_skips_users_with_no_unread_notifications(self):
        user = make_user()
        Notification.objects.create(
            recipient=user, notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='مقروء بالفعل', body='نص', is_read=True,
        )

        sent = send_daily_notification_digest()

        self.assertEqual(sent, 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_ignores_notifications_older_than_24_hours(self):
        user = make_user()
        old = Notification.objects.create(
            recipient=user, notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='قديم', body='نص',
        )
        Notification.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=2))

        sent = send_daily_notification_digest()

        self.assertEqual(sent, 0)
        self.assertEqual(len(mail.outbox), 0)


class CleanupOldReadNotificationsTaskTest(TestCase):

    def test_deletes_old_read_notifications_only(self):
        user = make_user()
        old_read = Notification.objects.create(
            recipient=user, notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='قديم مقروء', body='نص', is_read=True,
        )
        Notification.objects.filter(pk=old_read.pk).update(read_at=timezone.now() - timedelta(days=100))
        recent_read = Notification.objects.create(
            recipient=user, notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='حديث مقروء', body='نص', is_read=True, read_at=timezone.now(),
        )
        unread = Notification.objects.create(
            recipient=user, notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='غير مقروء', body='نص',
        )

        deleted = cleanup_old_read_notifications()

        self.assertEqual(deleted, 1)
        self.assertFalse(Notification.objects.filter(pk=old_read.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=recent_read.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=unread.pk).exists())

    def test_respects_custom_retention_days(self):
        user = make_user()
        notification = Notification.objects.create(
            recipient=user, notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='قديم نسبياً', body='نص', is_read=True,
        )
        Notification.objects.filter(pk=notification.pk).update(read_at=timezone.now() - timedelta(days=10))

        self.assertEqual(cleanup_old_read_notifications(retention_days=30), 0)
        self.assertEqual(cleanup_old_read_notifications(retention_days=5), 1)
