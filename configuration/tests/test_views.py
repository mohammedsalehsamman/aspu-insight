from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from configuration.models import JournalConfiguration

User = get_user_model()


def make_user(email, role, **kwargs):
    kwargs.setdefault('email_verified', True)
    return User.objects.create(email=email, full_name=email.split('@')[0], role=role, specialization='law', **kwargs)


class AdminJournalConfigurationViewTests(APITestCase):
    def setUp(self):
        self.admin = make_user('admin@example.com', 'admin')
        self.editor = make_user('editor@example.com', 'editor')
        self.url = reverse('admin-journal-configuration')

    def test_unauthenticated_denied(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_admin_forbidden_on_get(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_admin_forbidden_on_put(self):
        self.client.force_authenticate(user=self.editor)
        response = self.client.put(self.url, {'system_mode': 'full_closed'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_get_creates_singleton_on_first_access(self):
        self.assertFalse(JournalConfiguration.objects.exists())
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(JournalConfiguration.objects.count(), 1)
        self.assertEqual(response.data['system_mode'], 'full_open')

    def test_admin_put_updates_mode(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.put(self.url, {'system_mode': 'full_closed'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        config = JournalConfiguration.objects.get(pk=1)
        self.assertEqual(config.system_mode, 'full_closed')

    def test_admin_patch_updates_mode(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(self.url, {'system_mode': 'hybrid'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        config = JournalConfiguration.objects.get(pk=1)
        self.assertEqual(config.system_mode, 'hybrid')

    def test_admin_put_invalid_mode_rejected(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.put(self.url, {'system_mode': 'not_real'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_singleton_reused_across_requests(self):
        self.client.force_authenticate(user=self.admin)
        self.client.get(self.url)
        self.client.patch(self.url, {'system_mode': 'hybrid'}, format='json')
        self.assertEqual(JournalConfiguration.objects.count(), 1)
