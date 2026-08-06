from django.test import TestCase

from accounts.models import User


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
