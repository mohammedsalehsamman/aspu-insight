from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User


class RegisterAPITest(APITestCase):

    def setUp(self):
        cache.clear()
        self.url = reverse('auth:auth-register')
        self.valid_data = {
            'full_name': 'مستخدم اختبار',
            'email': 'newuser@example.com',
            'password': 'StrongPass123!',
            'password2': 'StrongPass123!',
            'role': 'author',
            'specialization': 'علوم الحاسوب',
        }

    def test_register_success(self):
        response = self.client.post(self.url, self.valid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('user', response.data)
        self.assertIn('message', response.data)
        self.assertTrue(User.objects.filter(email='newuser@example.com').exists())

    def test_register_email_verified_false_by_default(self):
        self.client.post(self.url, self.valid_data, format='json')
        user = User.objects.get(email='newuser@example.com')
        self.assertFalse(user.email_verified)

    def test_register_duplicate_email(self):
        self.client.post(self.url, self.valid_data, format='json')
        response = self.client.post(self.url, self.valid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_password_mismatch(self):
        data = {**self.valid_data, 'password2': 'DifferentPass123!'}
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_required_fields(self):
        response = self.client.post(self.url, {'email': 'a@b.com'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_admin_role_not_allowed(self):
        data = {**self.valid_data, 'role': 'admin'}
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_default_role_is_author(self):
        data = {k: v for k, v in self.valid_data.items() if k != 'role'}
        data['email'] = 'noroleset@example.com'
        self.client.post(self.url, data, format='json')
        user = User.objects.get(email='noroleset@example.com')
        self.assertEqual(user.role, 'author')
