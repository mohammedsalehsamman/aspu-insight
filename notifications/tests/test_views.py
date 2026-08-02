from django.urls import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from notifications.models import Notification, UserNotificationPreference
from notifications.tests.helpers import make_user


class NotificationListAPITest(TestCase):

    def setUp(self):
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
