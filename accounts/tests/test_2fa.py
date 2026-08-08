from datetime import timedelta

import pyotp
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.tests.helpers import make_user
from accounts.views import PreAuthToken


class Enable2FAAPITest(APITestCase):

    def setUp(self):
        self.url = reverse('auth:auth-2fa-enable')
        self.user = make_user(role='author')
        self.client.force_authenticate(user=self.user)

    def test_unauthenticated_denied(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_enable_generates_secret_and_provisioning_url(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('secret', response.data)
        self.assertIn('qr_code_url', response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.two_factor_secret, response.data['secret'])

    def test_already_enabled_returns_400(self):
        self.user.generate_2fa_secret()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class Confirm2FAAPITest(APITestCase):

    def setUp(self):
        cache.clear()
        self.url = reverse('auth:auth-2fa-confirm')
        self.user = make_user(role='author')
        self.user.generate_2fa_secret()
        self.client.force_authenticate(user=self.user)

    def test_missing_otp_code_returns_400(self):
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_correct_otp_confirms_and_keeps_secret(self):
        totp = pyotp.TOTP(self.user.two_factor_secret)
        response = self.client.post(self.url, {'otp_code': totp.now()}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.two_factor_secret)

    def test_wrong_otp_clears_secret(self):
        response = self.client.post(self.url, {'otp_code': '000000'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.two_factor_secret)


class LoginAndVerify2FAFlowTest(APITestCase):

    def setUp(self):
        cache.clear()
        self.login_url = reverse('auth:auth-login')
        self.verify_url = reverse('auth:auth-2fa-verify')
        self.user = make_user(role='author', password='TwoFAPass123!')
        self.user.generate_2fa_secret()

    def _login(self):
        return self.client.post(self.login_url, {
            'email': self.user.email,
            'password': 'TwoFAPass123!',
        }, format='json')

    def test_login_with_2fa_enabled_returns_pre_auth_token_not_access_token(self):
        response = self._login()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('requires_2fa'))
        self.assertIn('pre_auth_token', response.data)
        self.assertNotIn('access', response.data)

    def test_verify_with_correct_otp_returns_real_tokens(self):
        pre_auth_token = self._login().data['pre_auth_token']
        totp = pyotp.TOTP(self.user.two_factor_secret)
        response = self.client.post(self.verify_url, {
            'pre_auth_token': pre_auth_token,
            'otp_code': totp.now(),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_verify_with_wrong_otp_returns_400(self):
        pre_auth_token = self._login().data['pre_auth_token']
        response = self.client.post(self.verify_url, {
            'pre_auth_token': pre_auth_token,
            'otp_code': '000000',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_with_garbage_pre_auth_token_returns_400(self):
        response = self.client.post(self.verify_url, {
            'pre_auth_token': 'not-a-real-token',
            'otp_code': '123456',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verify_with_expired_pre_auth_token_returns_400(self):
        token = PreAuthToken()
        token['user_id'] = self.user.user_id
        token.set_exp(lifetime=timedelta(seconds=-1))
        totp = pyotp.TOTP(self.user.two_factor_secret)
        response = self.client.post(self.verify_url, {
            'pre_auth_token': str(token),
            'otp_code': totp.now(),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
