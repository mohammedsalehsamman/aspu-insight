from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from accounts.utils import create_token_for_user


class ChangePasswordAPITest(APITestCase):

    def setUp(self):
        self.url = reverse('auth:auth-change-password')
        self.user = User.objects.create_user(
            email='changepass@example.com',
            full_name='تغيير مرور',
            password='OldPass123!'
        )
        self.client.force_authenticate(user=self.user)

    def test_change_password_success(self):
        response = self.client.post(self.url, {
            'old_password': 'OldPass123!',
            'new_password': 'NewPass456!',
            'confirm_password': 'NewPass456!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass456!'))

    def test_change_password_wrong_old(self):
        response = self.client.post(self.url, {
            'old_password': 'WrongOldPass!',
            'new_password': 'NewPass456!',
            'confirm_password': 'NewPass456!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_mismatch(self):
        response = self.client.post(self.url, {
            'old_password': 'OldPass123!',
            'new_password': 'NewPass456!',
            'confirm_password': 'DifferentNew!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PasswordResetAPITest(APITestCase):

    def setUp(self):
        cache.clear()
        self.request_url = reverse('auth:auth-password-reset')
        self.confirm_url = reverse('auth:auth-password-reset-confirm')
        self.user = User.objects.create_user(
            email='resetpass@example.com',
            full_name='إعادة تعيين',
            password='OldPass123!',
            is_active=True
        )

    def test_password_reset_request(self):
        response = self.client.post(self.request_url, {'email': 'resetpass@example.com'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_password_reset_request_nonexistent_email(self):
        response = self.client.post(self.request_url, {'email': 'ghost@example.com'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_password_reset_confirm_success(self):
        raw_token = create_token_for_user(self.user, token_type='password_reset', expiry_hours=1)
        response = self.client.post(self.confirm_url, {
            'token': raw_token,
            'new_password': 'NewResetPass123!',
            'confirm_password': 'NewResetPass123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewResetPass123!'))

    def test_password_reset_confirm_invalid_token(self):
        response = self.client.post(self.confirm_url, {
            'token': 'badtoken',
            'new_password': 'NewPass123!',
            'confirm_password': 'NewPass123!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
