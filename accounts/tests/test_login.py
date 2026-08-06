from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User


class LoginAPITest(APITestCase):

    def setUp(self):
        self.url = reverse('auth:auth-login')
        self.user = User.objects.create_user(
            email='login@example.com',
            full_name='مستخدم تسجيل',
            password='LoginPass123!',
            is_active=True
        )

    def test_login_success(self):
        response = self.client.post(self.url, {
            'email': 'login@example.com',
            'password': 'LoginPass123!'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertIn('user', response.data)

    def test_login_wrong_password(self):
        response = self.client.post(self.url, {
            'email': 'login@example.com',
            'password': 'WrongPass!'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_nonexistent_email(self):
        response = self.client.post(self.url, {
            'email': 'notexist@example.com',
            'password': 'AnyPass123!'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_inactive_user(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.post(self.url, {
            'email': 'login@example.com',
            'password': 'LoginPass123!'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
