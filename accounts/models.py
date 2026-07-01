from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
import pyotp
from .managers import CustomUserManager


ROLE_CHOICES = [
    ('admin', 'مدير النظام'),
    ('editor', 'محرر'),
    ('reviewer', 'محكم'),
    ('reviewer_assistant', 'مساعد محكم'),
    ('author', 'باحث'),
    ('reader', 'قارئ'),
]


class User(AbstractBaseUser, PermissionsMixin):
    user_id = models.AutoField(primary_key=True)
    full_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='author')
    institution = models.CharField(max_length=200, blank=True)
    orcid_id = models.CharField(max_length=50, blank=True)
    profile_picture_url = models.URLField(max_length=500, blank=True, null=True)
    bio = models.TextField(blank=True)
    preferred_language = models.CharField(max_length=5, default='ar')
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False) 
    email_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(null=True, blank=True)
    specialization=models.DateTimeField(max_length=32,null=True,blank=False)
    
    two_factor_secret = models.CharField(max_length=32, blank=True,null=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    objects = CustomUserManager()

    class Meta:
        db_table = 'User'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def str(self):
        return f"{self.full_name} <{self.email}>"

    def generate_2fa_secret(self):
        self.two_factor_secret = pyotp.random_base32()
        self.save()

    def verify_otp(self, otp_code):
        if not self.two_factor_secret:
            return False
        totp = pyotp.TOTP(self.two_factor_secret)
        return totp.verify(otp_code, valid_window=2)

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_editor(self):
        return self.role == 'editor'

    @property
    def is_reviewer(self):
        return self.role in ['reviewer', 'reviewer_assistant']

    @property
    def is_author(self):
        return self.role == 'author'

    @property
    def is_reader(self):
        return self.role == 'reader'


class PasswordResetToken(models.Model):
    token_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reset_tokens', db_column='user_id')
    token_hash = models.CharField(max_length=255)
    token_type = models.CharField(
        max_length=20,
        choices=[('password_reset', 'Password Reset'), ('email_verify', 'Email Verification')],
        default='password_reset'
    )
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'PasswordResetToken'
        verbose_name = 'Password Reset Token'
        verbose_name_plural = 'Password Reset Tokens'

    def is_valid(self):
        return not self.is_used and self.expires_at > timezone.now()

    def str(self):
        return f"Token for {self.user.email} [{self.token_type}]"