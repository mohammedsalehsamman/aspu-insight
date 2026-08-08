import importlib

import pyotp
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.permissions import IsEmailVerified
from accounts.tests.helpers import make_user


class AxesBackendOrderIneffectiveLockoutTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse('auth:auth-login')
        self.user = make_user(role='author', password='CorrectPass123!')

    def test_correct_password_still_succeeds_after_reaching_the_failure_limit(self):
        for _ in range(4):
            self.client.post(self.url, {
                'email': self.user.email, 'password': 'WrongPass!',
            }, format='json')
        response = self.client.post(self.url, {
            'email': self.user.email, 'password': 'CorrectPass123!',
        }, format='json')
        self.assertNotEqual(
            response.status_code, status.HTTP_200_OK,
            "Correct credentials still succeeded after 4 recorded failures — "
            "AxesStandaloneBackend never runs because EmailBackend (checked first in "
            "AUTHENTICATION_BACKENDS) already returns a valid user."
        )


class Verify2FAOTPBruteForceTests(APITestCase):

    def setUp(self):
        cache.clear()
        self.login_url = reverse('auth:auth-login')
        self.verify_url = reverse('auth:auth-2fa-verify')
        self.user = make_user(role='author', password='CorrectPass123!')
        self.user.generate_2fa_secret()
        login_response = self.client.post(self.login_url, {
            'email': self.user.email, 'password': 'CorrectPass123!',
        }, format='json')
        self.pre_auth_token = login_response.data['pre_auth_token']

    def test_otp_brute_force_is_not_locked_out(self):
        for _ in range(10):
            self.client.post(self.verify_url, {
                'pre_auth_token': self.pre_auth_token, 'otp_code': '000000',
            }, format='json')
        totp = pyotp.TOTP(self.user.two_factor_secret)
        response = self.client.post(self.verify_url, {
            'pre_auth_token': self.pre_auth_token, 'otp_code': totp.now(),
        }, format='json')
        self.assertNotEqual(
            response.status_code, status.HTTP_200_OK,
            "OTP brute force was not locked out even after 10 wrong attempts — "
            "Verify2FAView bypasses django-axes because it never calls authenticate()."
        )


class AxesLockoutNowEnforcedTests(APITestCase):
    """Positive proof for the A1 fix: AxesStandaloneBackend moved first in
    AUTHENTICATION_BACKENDS (settings.py) so it actually vetoes a correct-password login
    once AXES_FAILURE_LIMIT (4) wrong attempts were recorded."""

    def setUp(self):
        cache.clear()
        self.url = reverse('auth:auth-login')
        self.user = make_user(role='author', password='CorrectPass123!')

    def test_correct_password_is_rejected_after_reaching_the_failure_limit(self):
        for _ in range(4):
            self.client.post(self.url, {
                'email': self.user.email, 'password': 'WrongPass!',
            }, format='json')
        response = self.client.post(self.url, {
            'email': self.user.email, 'password': 'CorrectPass123!',
        }, format='json')
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)


class Verify2FAOTPLockoutEnforcedTests(APITestCase):
    """Positive proof for the A2 fix: a per-user cache counter (accounts/utils.py) now locks
    out OTP verification after OTP_MAX_ATTEMPTS (5) wrong codes, even across a fresh
    pre_auth_token, since the counter is keyed on user_id not on the token."""

    def setUp(self):
        cache.clear()
        self.login_url = reverse('auth:auth-login')
        self.verify_url = reverse('auth:auth-2fa-verify')
        self.user = make_user(role='author', password='CorrectPass123!')
        self.user.generate_2fa_secret()

    def _get_pre_auth_token(self):
        login_response = self.client.post(self.login_url, {
            'email': self.user.email, 'password': 'CorrectPass123!',
        }, format='json')
        return login_response.data['pre_auth_token']

    def test_correct_otp_is_rejected_after_five_wrong_attempts(self):
        pre_auth_token = self._get_pre_auth_token()
        for _ in range(5):
            self.client.post(self.verify_url, {
                'pre_auth_token': pre_auth_token, 'otp_code': '000000',
            }, format='json')
        totp = pyotp.TOTP(self.user.two_factor_secret)
        response = self.client.post(self.verify_url, {
            'pre_auth_token': pre_auth_token, 'otp_code': totp.now(),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_lockout_survives_a_fresh_pre_auth_token(self):
        # The attacker already knows the password (realistic threat model) and simply
        # requests a new token once the 5-minute one is close to expiry — the lockout must
        # still hold because it is keyed on the user, not the token.
        pre_auth_token = self._get_pre_auth_token()
        for _ in range(5):
            self.client.post(self.verify_url, {
                'pre_auth_token': pre_auth_token, 'otp_code': '000000',
            }, format='json')
        fresh_token = self._get_pre_auth_token()
        totp = pyotp.TOTP(self.user.two_factor_secret)
        response = self.client.post(self.verify_url, {
            'pre_auth_token': fresh_token, 'otp_code': totp.now(),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_correct_otp_resets_the_counter(self):
        pre_auth_token = self._get_pre_auth_token()
        self.client.post(self.verify_url, {
            'pre_auth_token': pre_auth_token, 'otp_code': '000000',
        }, format='json')
        totp = pyotp.TOTP(self.user.two_factor_secret)
        response = self.client.post(self.verify_url, {
            'pre_auth_token': pre_auth_token, 'otp_code': totp.now(),
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class IsEmailVerifiedNeverEnforcedTests(TestCase):
    APPS = [
        'accounts', 'research', 'committees', 'ai_service', 'dashboard',
        'notifications', 'assistantReview', 'editorReview', 'configuration',
        'researchHistory',
    ]

    def test_is_email_verified_is_attached_to_at_least_one_view(self):
        found = []
        for app in self.APPS:
            try:
                views_module = importlib.import_module(f'{app}.views')
            except ModuleNotFoundError:
                continue
            for name in dir(views_module):
                permission_classes = getattr(getattr(views_module, name), 'permission_classes', None)
                if permission_classes and IsEmailVerified in permission_classes:
                    found.append(f'{app}.views.{name}')

        self.assertTrue(
            found,
            "IsEmailVerified is defined and unit-tested but not attached to any view's "
            "permission_classes across the whole project — unverified emails are "
            "currently unrestricted everywhere."
        )
