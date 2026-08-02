from unittest import mock

from django.core.cache import cache
from django.urls import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from notifications.cache import ws_ticket_cache_key
from notifications.models import DeviceToken, Notification, UserNotificationPreference
from notifications.services import NotificationService
from notifications.tests.helpers import make_user


class NotificationListAPITest(TestCase):

    def setUp(self):
        cache.clear()  # LocMemCache لا يُصفَّى تلقائياً بين الاختبارات كما تفعل معاملة القاعدة
        self.user = make_user()
        self.other_user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _create_notification(self, recipient, is_read=False):
        return Notification.objects.create(
            recipient=recipient,
            notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='عنوان', body='نص', is_read=is_read,
        )

    def test_list_only_returns_own_notifications(self):
        self._create_notification(self.user)
        self._create_notification(self.other_user)  # يجب ألا تظهر لهذا المستخدم

        response = self.client.get(reverse('notification-list'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_unauthenticated_request_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse('notification-list'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unread_count(self):
        self._create_notification(self.user, is_read=False)
        self._create_notification(self.user, is_read=True)

        response = self.client.get(reverse('notification-unread-count'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['unread_count'], 1)

    def test_mark_read(self):
        notification = self._create_notification(self.user)

        response = self.client.post(reverse('notification-mark-read', args=[notification.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_cannot_mark_other_users_notification_as_read(self):
        notification = self._create_notification(self.other_user)

        response = self.client.post(reverse('notification-mark-read', args=[notification.pk]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_mark_all_read(self):
        self._create_notification(self.user)
        self._create_notification(self.user)
        self._create_notification(self.other_user)  # يجب ألا يتأثر

        response = self.client.post(reverse('notification-mark-all-read'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['updated'], 2)
        self.assertEqual(Notification.objects.filter(recipient=self.user, is_read=False).count(), 0)
        self.assertEqual(Notification.objects.filter(recipient=self.other_user, is_read=False).count(), 1)


class NotificationGroupedListAPITest(TestCase):
    """تجميع وقت القراءة عبر group_key (Phase 6) — لا دمج وقت الكتابة، كل صف Notification
    يبقى مستقلاً؛ هذه النقطة فقط تعرض ملخصاً لكل مجموعة."""

    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_unauthenticated_request_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse('notification-grouped-list'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_groups_notifications_sharing_group_key(self):
        for i in range(3):
            Notification.objects.create(
                recipient=self.user, notification_type=Notification.NotificationType.ROLE_CHANGED,
                title=f"تغيير {i}", body='نص', group_key='role_changed:1:1', is_read=(i == 0),
            )
        Notification.objects.create(
            recipient=self.user, notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='إعلان', body='نص', group_key='system_announcement:0:0',
        )

        response = self.client.get(reverse('notification-grouped-list'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        role_group = next(g for g in response.data if g['group_key'] == 'role_changed:1:1')
        self.assertEqual(role_group['count'], 3)
        self.assertEqual(role_group['unread_count'], 2)
        self.assertEqual(role_group['title'], 'تغيير 2')  # أحدث إشعار في المجموعة

    def test_excludes_empty_group_key(self):
        Notification.objects.create(
            recipient=self.user, notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='بلا مجموعة', body='نص', group_key='',
        )

        response = self.client.get(reverse('notification-grouped-list'))

        self.assertEqual(response.data, [])

    def test_only_returns_own_notifications(self):
        other_user = make_user()
        Notification.objects.create(
            recipient=other_user, notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='لغيري', body='نص', group_key='system_announcement:0:0',
        )

        response = self.client.get(reverse('notification-grouped-list'))

        self.assertEqual(response.data, [])


class NotificationPreferenceAPITest(TestCase):

    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_unauthenticated_request_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse('notification-preferences'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_returns_effective_defaults_without_creating_rows(self):
        response = self.client.get(reverse('notification-preferences'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), len(Notification.NotificationType.choices))
        self.assertEqual(UserNotificationPreference.objects.filter(user=self.user).count(), 0)

    def test_patch_creates_row_only_for_the_sent_type(self):
        response = self.client.patch(
            reverse('notification-preferences'),
            [{'notification_type': Notification.NotificationType.PAPER_PUBLISHED, 'email_enabled': False}],
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(UserNotificationPreference.objects.filter(user=self.user).count(), 1)
        preference = UserNotificationPreference.objects.get(
            user=self.user, notification_type=Notification.NotificationType.PAPER_PUBLISHED,
        )
        self.assertFalse(preference.email_enabled)
        self.assertTrue(preference.in_app_enabled)  # لم يُرسَل، فيُحافَظ على القيمة الفعّالة الحالية

    def test_cannot_disable_in_app_for_non_disableable_type(self):
        response = self.client.patch(
            reverse('notification-preferences'),
            [{'notification_type': Notification.NotificationType.ROLE_CHANGED, 'in_app_enabled': False}],
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data[0]['in_app_enabled'])
        preference = UserNotificationPreference.objects.get(
            user=self.user, notification_type=Notification.NotificationType.ROLE_CHANGED,
        )
        self.assertTrue(preference.in_app_enabled)


class NotificationWSTicketAPITest(TestCase):

    def setUp(self):
        cache.clear()
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_unauthenticated_request_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(reverse('notification-ws-ticket'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_issues_ticket_resolving_to_requesting_user(self):
        response = self.client.post(reverse('notification-ws-ticket'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ticket = response.data['ticket']
        self.assertEqual(cache.get(ws_ticket_cache_key(ticket)), self.user.pk)

    def test_two_requests_issue_different_tickets(self):
        first = self.client.post(reverse('notification-ws-ticket')).data['ticket']
        second = self.client.post(reverse('notification-ws-ticket')).data['ticket']
        self.assertNotEqual(first, second)


class NotificationUnreadCountCacheTest(TestCase):
    """يثبّت أن عدّاد غير المقروء يُقرأ من الـ Cache بين الطلبات، ويُبطَل صراحة عند كل كتابة
    تغيّر حالة غير مقروء — لا اعتماد على TTL وحده (راجع notifications/cache.py)."""

    def setUp(self):
        cache.clear()
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _create_notification_via_service(self):
        # push_ws_notification.delay يُجدوَل دوماً عبر on_commit، وSYSTEM_ANNOUNCEMENT فيه
        # email=True افتراضياً فيُجدوِل send_email_notification.delay أيضاً — .delay() الحقيقي
        # يحاول الاتصال بناقل Celery الفعلي حتى مع تنفيذ callbacks الاختبار، فنموّه الاثنين
        # لعزل اختبار إبطال الـ Cache عن ناقل Celery (نفس نمط FullEmailDispatchTest).
        with mock.patch('notifications.tasks.send_email_notification.delay'):
            with mock.patch('notifications.tasks.push_ws_notification.delay'):
                with self.captureOnCommitCallbacks(execute=True):
                    return NotificationService.create_notification(
                        recipient=self.user,
                        notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
                        context={'fallback_title': 'عنوان', 'fallback_body': 'نص'},
                    )

    def test_value_stays_cached_until_explicit_invalidation(self):
        self._create_notification_via_service()
        first = self.client.get(reverse('notification-unread-count'))
        self.assertEqual(first.data['unread_count'], 1)

        # إنشاء مباشر عبر الـ ORM (متجاوزاً NotificationService) — لا إبطال، فتبقى القيمة
        # القديمة في الـ Cache حتى لو تغيّرت الحقيقة في القاعدة.
        Notification.objects.create(
            recipient=self.user, notification_type=Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
            title='ثانٍ', body='نص',
        )
        second = self.client.get(reverse('notification-unread-count'))
        self.assertEqual(second.data['unread_count'], 1)

    def test_create_notification_invalidates_cache(self):
        self.client.get(reverse('notification-unread-count'))  # يزرع 0 في الـ Cache

        self._create_notification_via_service()

        response = self.client.get(reverse('notification-unread-count'))
        self.assertEqual(response.data['unread_count'], 1)

    def test_mark_all_read_invalidates_cache(self):
        self._create_notification_via_service()
        self.client.get(reverse('notification-unread-count'))  # يزرع 1 في الـ Cache

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('notification-mark-all-read'))

        response = self.client.get(reverse('notification-unread-count'))
        self.assertEqual(response.data['unread_count'], 0)

    def test_mark_read_invalidates_cache(self):
        notification = self._create_notification_via_service()
        self.client.get(reverse('notification-unread-count'))  # يزرع 1 في الـ Cache

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('notification-mark-read', args=[notification.pk]))

        response = self.client.get(reverse('notification-unread-count'))
        self.assertEqual(response.data['unread_count'], 0)


class DeviceTokenAPITest(TestCase):

    def setUp(self):
        self.user = make_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_unauthenticated_request_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(reverse('notification-device-tokens'), {'token': 'x', 'platform': 'web'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_register_creates_active_token_for_current_user(self):
        response = self.client.post(
            reverse('notification-device-tokens'), {'token': 'abc123', 'platform': 'android'},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        device_token = DeviceToken.objects.get(token='abc123')
        self.assertEqual(device_token.user, self.user)
        self.assertTrue(device_token.is_active)

    def test_registering_same_token_reassigns_to_new_user(self):
        """جهاز واحد قد يُستخدم من حساب آخر لاحقاً (تسجيل خروج/دخول) — الرمز نفسه لا يتغيّر."""
        previous_owner = make_user()
        DeviceToken.objects.create(user=previous_owner, token='shared-device', platform='ios', is_active=False)

        response = self.client.post(
            reverse('notification-device-tokens'), {'token': 'shared-device', 'platform': 'ios'},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(DeviceToken.objects.filter(token='shared-device').count(), 1)
        device_token = DeviceToken.objects.get(token='shared-device')
        self.assertEqual(device_token.user, self.user)
        self.assertTrue(device_token.is_active)

    def test_delete_removes_own_token(self):
        DeviceToken.objects.create(user=self.user, token='mine', platform='web')

        response = self.client.delete(reverse('notification-device-tokens'), {'token': 'mine'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(DeviceToken.objects.filter(token='mine').exists())

    def test_cannot_delete_another_users_token(self):
        other_user = make_user()
        DeviceToken.objects.create(user=other_user, token='not-mine', platform='web')

        response = self.client.delete(reverse('notification-device-tokens'), {'token': 'not-mine'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(DeviceToken.objects.filter(token='not-mine').exists())

    def test_delete_without_token_is_bad_request(self):
        response = self.client.delete(reverse('notification-device-tokens'), {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
