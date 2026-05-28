from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User, PasswordResetToken


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['email', 'full_name', 'role', 'is_active', 'email_verified', 'created_at']
    list_filter = ['role', 'is_active', 'email_verified']
    search_fields = ['email', 'full_name', 'institution']
    ordering = ['-created_at']

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('المعلومات الشخصية'), {'fields': ('full_name', 'institution', 'orcid_id', 'bio', 'profile_picture_url', 'preferred_language')}),
        (_('الأدوار والصلاحيات'), {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'email_verified', 'groups', 'user_permissions')}),
        (_('التواريخ'), {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    readonly_fields = ['created_at', 'updated_at', 'last_login']

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'role', 'password1', 'password2'),
        }),
    )

    ordering = ['-created_at']


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'token_type', 'expires_at', 'is_used', 'created_at']
    list_filter = ['token_type', 'is_used']
    search_fields = ['user__email']
    readonly_fields = ['token_hash', 'created_at']
