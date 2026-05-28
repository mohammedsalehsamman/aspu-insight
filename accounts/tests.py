
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from datetime import timedelta

from .models import User, PasswordResetToken
from .utils import create_token_for_user, verify_token, hash_token

class UserModelTest(TestCase):

    def test_create_user(self):
        user = User.objects.create_user(
            email='test@example.com',
            full_name='اختبار مستخدم',
            password='TestPass123!'
        )
        self.assertEqual(user.email, 'test@example.com')
        self.assertEqual(user.role, 'author')
        self.assertFalse(user.email_verified)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password('TestPass123!'))

    def test_create_superuser(self):
        superuser = User.objects.create_superuser(
            email='admin@example.com',
            full_name='مدير النظام',
            password='AdminPass123!'
        )
        self.assertEqual(superuser.role, 'admin')
        self.assertTrue(superuser.is_staff)
        self.assertTrue(superuser.is_superuser)
        self.assertTrue(superuser.email_verified)

    def test_email_required(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email='', full_name='اسم', password='pass')

    def test_email_unique(self):
        User.objects.create_user(email='unique@example.com', full_name='مستخدم أول', password='pass123')
        with self.assertRaises(Exception):
            User.objects.create_user(email='unique@example.com', full_name='مستخدم ثاني', password='pass456')

    def test_role_properties(self):
        user = User.objects.create_user(email='a@a.com', full_name='test', password='pass', role='author')
        self.assertTrue(user.is_author)
        self.assertFalse(user.is_admin)
        self.assertFalse(user.is_editor)

    def test_str_representation(self):
        user = User.objects.create_user(email='str@test.com', full_name='اختبار', password='pass')
        self.assertIn('اختبار', str(user))
        self.assertIn('str@test.com', str(user))

class RegisterAPITest(APITestCase):

    def setUp(self):
        self.url = reverse('auth:auth-register')
        self.valid_data = {
            'full_name': 'مستخدم اختبار',
            'email': 'newuser@example.com',
            'password': 'StrongPass123!',
            'password2': 'StrongPass123!',
            'role': 'author',
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
        # استخدام ثانٍ يجب أن يفشل
        response = self.client.post(self.url, {'token': raw_token}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

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


class IsEmailVerifiedPermissionTest(TestCase):

    def test_verified_user_has_permission(self):
        from .permissions import IsEmailVerified
        from unittest.mock import MagicMock

        perm = IsEmailVerified()
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.email_verified = True

        self.assertTrue(perm.has_permission(request, None))

    def test_unverified_user_denied(self):
        from .permissions import IsEmailVerified
        from unittest.mock import MagicMock

        perm = IsEmailVerified()
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.email_verified = False

        self.assertFalse(perm.has_permission(request, None))
