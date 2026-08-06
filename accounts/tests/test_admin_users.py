from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User


class AdminUserAPITest(APITestCase):

    def setUp(self):
        self.list_url = reverse('admin-api:admin-user-list')
        self.admin = User.objects.create_user(
            email='admin@example.com',
            full_name='المدير',
            password='AdminPass123!',
            role='admin',
            email_verified=True
        )
        self.regular_user = User.objects.create_user(
            email='regular@example.com',
            full_name='مستخدم عادي',
            password='UserPass123!',
            role='author'
        )

    def test_admin_can_list_users(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_non_admin_cannot_list_users(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_list_users(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_can_filter_by_role(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.list_url, {'role': 'author'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_can_verify_user_email(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse('admin-api:admin-verify-email', kwargs={'user_id': self.regular_user.user_id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.regular_user.refresh_from_db()
        self.assertTrue(self.regular_user.email_verified)

    def test_admin_can_deactivate_user(self):
        self.client.force_authenticate(user=self.admin)
        url = reverse('admin-api:admin-user-detail', kwargs={'user_id': self.regular_user.user_id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.regular_user.refresh_from_db()
        self.assertFalse(self.regular_user.is_active)
