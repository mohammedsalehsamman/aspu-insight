from django.test import TestCase
from django.utils import timezone

from notifications.models import Notification
from notifications.services import NotificationService
from notifications.tests.helpers import make_paper, make_user


class NotificationModelTest(TestCase):

    def test_mark_read_sets_is_read_and_read_at(self):
        user = make_user()
        notification = Notification.objects.create(
            recipient=user,
            notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='عنوان',
            body='نص',
        )
        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)

        notification.mark_read()

        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)
        self.assertLessEqual(notification.read_at, timezone.now())

    def test_mark_read_is_idempotent(self):
        user = make_user()
        notification = Notification.objects.create(
            recipient=user,
            notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='عنوان',
            body='نص',
        )
        notification.mark_read()
        first_read_at = notification.read_at

        notification.mark_read()  # لا يجب أن يغيّر read_at في المرة الثانية
        self.assertEqual(notification.read_at, first_read_at)

    def test_group_key_and_target_repr_survive_target_deletion(self):
        # group_key يُحسب في NotificationService.create_notification وقت الإنشاء، وليس
        # تلقائياً في Notification.save() — لذا نمر عبر الخدمة لا .objects.create() المباشر.
        author = make_user(role='author')
        paper = make_paper(author=author)
        notification = NotificationService.create_notification(
            recipient=author,
            notification_type=Notification.NotificationType.PAPER_SUBMITTED,
            target=paper,
            target_repr=paper.title,
            context={'fallback_title': 'عنوان', 'fallback_body': 'نص'},
        )
        expected_group_key = (
            f"{Notification.NotificationType.PAPER_SUBMITTED}:"
            f"{notification.target_content_type_id}:{paper.pk}"
        )
        self.assertEqual(notification.group_key, expected_group_key)

        paper.delete()
        notification.refresh_from_db()
        self.assertIsNone(notification.target)  # الهدف حُذف، لكن اللقطة النصية تبقى
        self.assertEqual(notification.target_repr, 'بحث تجريبي')
