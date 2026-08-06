from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, PasswordResetToken
from accounts.utils import create_token_for_user, hash_token


class EmailVerifyAPITest(APITestCase):

    def setUp(self):
        self.url = reverse('auth:auth-verify-email')
        self.user = User.objects.create_user(
            email='unverified@example.com',
            full_name='غير موثق',
            password='Pass123!',
            email_verified=False
        )

    def test_verify_email_success(self):
        raw_token = create_token_for_user(self.user, token_type='email_verify', expiry_hours=24)
        response = self.client.post(self.url, {'token': raw_token}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)

    def test_verify_email_invalid_token(self):
        response = self.client.post(self.url, {'token': 'invalidtoken'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_email_expired_token(self):
        raw_token = create_token_for_user(self.user, token_type='email_verify', expiry_hours=24)
        token_hash = hash_token(raw_token)
        token_obj = PasswordResetToken.objects.get(token_hash=token_hash)
        token_obj.expires_at = timezone.now() - timedelta(hours=1)
        token_obj.save()

        response = self.client.post(self.url, {'token': raw_token}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_email_used_token(self):
        raw_token = create_token_for_user(self.user, token_type='email_verify', expiry_hours=24)
        self.client.post(self.url, {'token': raw_token}, format='json')

        response = self.client.post(self.url, {'token': raw_token}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
