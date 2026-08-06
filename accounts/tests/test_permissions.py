from unittest.mock import MagicMock

from django.test import TestCase

from accounts.permissions import IsEmailVerified


class IsEmailVerifiedPermissionTest(TestCase):

    def test_verified_user_has_permission(self):
        perm = IsEmailVerified()
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.email_verified = True

        self.assertTrue(perm.has_permission(request, None))

    def test_unverified_user_denied(self):
        perm = IsEmailVerified()
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.email_verified = False

        self.assertFalse(perm.has_permission(request, None))
