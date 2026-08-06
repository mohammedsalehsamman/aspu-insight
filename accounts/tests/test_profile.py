from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User


class ProfileAPITest(APITestCase):

    def setUp(self):
        self.url = reverse('auth:auth-profile')
        self.user = User.objects.create_user(
            email='profile@example.com',
            full_name='مستخدم الملف',
            password='ProfilePass123!'
        )
        self.client.force_authenticate(user=self.user)

    def test_get_profile_authenticated(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'profile@example.com')

    def test_get_profile_unauthenticated(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_profile_patch(self):
        response = self.client.patch(self.url, {'bio': 'سيرتي الذاتية'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.bio, 'سيرتي الذاتية')

    def test_cannot_update_role_via_profile(self):
        response = self.client.patch(self.url, {'role': 'admin'}, format='json')
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.role, 'admin')

    def test_cannot_update_email_via_profile(self):
        response = self.client.patch(self.url, {'email': 'hacker@evil.com'}, format='json')
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'profile@example.com')
