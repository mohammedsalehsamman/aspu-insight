from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager):
    def create_user(self, email, full_name, password=None, **extra_fields):
        if not email:
            raise ValueError(_('البريد الإلكتروني مطلوب'))
        if not full_name:
            raise ValueError(_('الاسم الكامل مطلوب'))
        email = self.normalize_email(email)
        user = self.model(email=email, full_name=full_name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, full_name, password=None, **extra_fields):
        extra_fields.setdefault('role', 'admin')
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('email_verified', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('المستخدم المميز يجب أن يكون is_staff=True'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('المستخدم المميز يجب أن يكون is_superuser=True'))

        return self.create_user(email, full_name, password, **extra_fields)
