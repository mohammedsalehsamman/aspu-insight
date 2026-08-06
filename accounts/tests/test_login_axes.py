from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.tests.helpers import make_user
from axes.models import AccessAttempt


class AxesFailureTrackingTests(APITestCase):
    def setUp(self):
        self.url = reverse('auth:auth-login')
        self.user = make_user(role='author', password='CorrectPass123!')

    def _wrong_attempt(self):
        return self.client.post(self.url, {
            'email': self.user.email, 'password': 'WrongPass!',
        }, format='json')

    def test_wrong_password_creates_an_access_attempt_record(self):
        self.assertEqual(AccessAttempt.objects.count(), 0)
        self._wrong_attempt()
        self.assertEqual(AccessAttempt.objects.count(), 1)

    def test_repeated_wrong_passwords_increment_the_same_record(self):
        for _ in range(3):
            self._wrong_attempt()
        attempt = AccessAttempt.objects.get()
        self.assertEqual(attempt.failures_since_start, 3)

    def test_correct_password_does_not_create_an_access_attempt_record(self):
        self.client.post(self.url, {
            'email': self.user.email, 'password': 'CorrectPass123!',
        }, format='json')
        self.assertEqual(AccessAttempt.objects.count(), 0)
