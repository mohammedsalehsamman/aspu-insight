from django.contrib import admin

from notifications.models import (
    Notification,
    NotificationDelivery,
    NotificationTemplate,
    UserNotificationPreference,
    DeviceToken,
)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['id', 'recipient', 'notification_type', 'level', 'is_read', 'created_at']
    list_filter = ['notification_type', 'level', 'is_read']
    search_fields = ['recipient__email', 'recipient__full_name', 'title']
    readonly_fields = ['created_at']
    ordering = ['-created_at']


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    list_display = ['id', 'notification', 'channel', 'status', 'attempt_count', 'sent_at']
    list_filter = ['channel', 'status']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ['notification_type', 'channel', 'language', 'is_active']
    list_filter = ['channel', 'language', 'is_active']
    search_fields = ['notification_type']


@admin.register(UserNotificationPreference)
class UserNotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'notification_type', 'in_app_enabled', 'email_enabled', 'push_enabled']
    list_filter = ['notification_type', 'in_app_enabled', 'email_enabled', 'push_enabled']
    search_fields = ['user__email', 'user__full_name']


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'platform', 'is_active', 'last_used_at', 'created_at']
    list_filter = ['platform', 'is_active']
    search_fields = ['user__email']
