from django.test import TestCase

from notifications.models import Notification, NotificationTemplate, UserNotificationPreference
from notifications.services import NON_DISABLEABLE_IN_APP, NotificationService
from notifications.tests.helpers import make_user


class ResolveChannelsTest(TestCase):

    def test_defaults_used_when_no_preference_row(self):
        user = make_user()
        channels = NotificationService._resolve_channels(
            user, Notification.NotificationType.PAPER_PUBLISHED,
        )
        # PAPER_PUBLISHED افتراضياً: in_app + email
        self.assertEqual(channels, {'in_app': True, 'email': True, 'push': False})

    def test_override_row_takes_precedence(self):
        user = make_user()
        UserNotificationPreference.objects.create(
            user=user, notification_type=Notification.NotificationType.PAPER_PUBLISHED,
            in_app_enabled=True, email_enabled=False, push_enabled=False,
        )
        channels = NotificationService._resolve_channels(
            user, Notification.NotificationType.PAPER_PUBLISHED,
        )
        self.assertEqual(channels, {'in_app': True, 'email': False, 'push': False})

    def test_non_disableable_in_app_cannot_be_turned_off(self):
        user = make_user()
        for notification_type in NON_DISABLEABLE_IN_APP:
            UserNotificationPreference.objects.create(
                user=user, notification_type=notification_type,
                in_app_enabled=False, email_enabled=False, push_enabled=False,
            )
            channels = NotificationService._resolve_channels(user, notification_type)
            self.assertTrue(channels['in_app'], msg=f"{notification_type} must stay in_app-enabled")


class RenderTemplateTest(TestCase):
    # نستخدم DISCUSSION_MENTION هنا لأنه النوع الوحيد غير المبذور مسبقاً بقالب in_app/ar
    # عبر migration 0002 — يتفادى تعارض unique_together مع بيانات الهجرة.

    def test_uses_active_template_for_language(self):
        NotificationTemplate.objects.create(
            notification_type=Notification.NotificationType.DISCUSSION_MENTION,
            channel='in_app', language='ar',
            subject_template='عنوان: {{ x }}', body_template='نص: {{ x }}',
        )
        title, body = NotificationService._render(
            Notification.NotificationType.DISCUSSION_MENTION, 'in_app', 'ar', {'x': 'قيمة'},
        )
        self.assertEqual(title, 'عنوان: قيمة')
        self.assertEqual(body, 'نص: قيمة')

    def test_falls_back_to_arabic_when_language_missing(self):
        NotificationTemplate.objects.create(
            notification_type=Notification.NotificationType.DISCUSSION_MENTION,
            channel='in_app', language='ar',
            subject_template='عنوان عربي', body_template='نص عربي',
        )
        title, body = NotificationService._render(
            Notification.NotificationType.DISCUSSION_MENTION, 'in_app', 'en', {},
        )
        self.assertEqual(title, 'عنوان عربي')

    def test_falls_back_to_context_when_no_template_row(self):
        title, body = NotificationService._render(
            Notification.NotificationType.DISCUSSION_MENTION, 'in_app', 'ar',
            {'fallback_title': 'افتراضي', 'fallback_body': 'نص افتراضي'},
        )
        self.assertEqual(title, 'افتراضي')
        self.assertEqual(body, 'نص افتراضي')


class CreateNotificationTest(TestCase):

    def test_creates_notification_row(self):
        user = make_user()
        notification = NotificationService.create_notification(
            recipient=user,
            notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            context={'fallback_title': 'عنوان', 'fallback_body': 'نص'},
        )
        self.assertIsNotNone(notification)
        self.assertEqual(Notification.objects.filter(recipient=user).count(), 1)

    def test_skips_creation_when_in_app_disabled(self):
        user = make_user()
        UserNotificationPreference.objects.create(
            user=user, notification_type=Notification.NotificationType.PAPER_STATUS_CHANGED,
            in_app_enabled=False, email_enabled=False, push_enabled=False,
        )
        notification = NotificationService.create_notification(
            recipient=user,
            notification_type=Notification.NotificationType.PAPER_STATUS_CHANGED,
            context={'fallback_title': 'عنوان', 'fallback_body': 'نص'},
        )
        self.assertIsNone(notification)
        self.assertEqual(Notification.objects.filter(recipient=user).count(), 0)
