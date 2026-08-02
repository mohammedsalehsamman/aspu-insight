from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils import timezone


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        PAPER_SUBMITTED = 'paper_submitted', 'تقديم بحث جديد'
        PAPER_STATUS_CHANGED = 'paper_status_changed', 'تغيّر حالة البحث'
        PAPER_PUBLISHED = 'paper_published', 'نشر البحث'
        ASSISTANT_REVIEW_RECEIVED = 'assistant_review_received', 'مراجعة مساعد المحرر'
        EDITOR_REVIEW_RECEIVED = 'editor_review_received', 'مراجعة المحرر'
        COMMITTEE_REVIEW_RECEIVED = 'committee_review_received', 'قرار لجنة التحكيم'
        COMMITTEE_DEADLINE_APPROACHING = 'committee_deadline_approaching', 'اقتراب موعد اللجنة'
        COMMITTEE_DEADLINE_EXPIRED = 'committee_deadline_expired', 'انتهاء مهلة اللجنة'
        EDITOR_ASSIGNED = 'editor_assigned', 'تعيين محرر'
        REVIEWER_ASSIGNED_TO_COMMITTEE = 'reviewer_assigned_to_committee', 'تعيين محكم في لجنة'
        ROLE_CHANGED = 'role_changed', 'تغيّر الصلاحية'
        SYSTEM_ANNOUNCEMENT = 'system_announcement', 'إعلان من الإدارة'
        # محجوزة لتوسعات مستقبلية (تطبيقات لا توجد اليوم: تعليقات/نقاشات، أعداد/إصدارات المجلة).
        DISCUSSION_MENTION = 'discussion_mention', 'إشارة في نقاش'
        ISSUE_PUBLISHED = 'issue_published', 'نشر عدد جديد'

    class Level(models.TextChoices):
        INFO = 'info', 'معلومة'
        SUCCESS = 'success', 'نجاح'
        WARNING = 'warning', 'تنبيه'
        CRITICAL = 'critical', 'حرج'

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='triggered_notifications',
    )
    notification_type = models.CharField(max_length=40, choices=NotificationType.choices, db_index=True)
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)

    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default='')
    data = models.JSONField(default=dict, blank=True)

    target_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    target_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    target = GenericForeignKey('target_content_type', 'target_object_id')
    # لقطة نصية تبقى صحيحة حتى لو حُذف الهدف لاحقاً (لا GenericRelation على النماذج الأخرى).
    target_repr = models.CharField(max_length=255, blank=True, default='')

    group_key = models.CharField(max_length=80, blank=True, default='', db_index=True)

    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'Notification'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at'], name='notif_recipient_unread_idx'),
            models.Index(fields=['recipient', '-created_at'], name='notif_recipient_created_idx'),
            models.Index(fields=['group_key'], name='notif_group_key_idx'),
            models.Index(fields=['target_content_type', 'target_object_id'], name='notif_target_idx'),
        ]

    def __str__(self):
        return f"{self.notification_type} -> {self.recipient_id}"

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
            from notifications.cache import invalidate_unread_count
            transaction.on_commit(lambda: invalidate_unread_count(self.recipient_id))


class NotificationDelivery(models.Model):
    """تتبّع إرسال إشعار عبر قناة خارجية (بريد/جوال) وعدد محاولات إعادة الإرسال.

    لا يُنشأ صف لقناة in_app: صف Notification نفسه + is_read هو حالة تسليمها.
    """

    class Channel(models.TextChoices):
        EMAIL = 'email', 'بريد إلكتروني'
        PUSH = 'push', 'إشعار جوال'

    class Status(models.TextChoices):
        PENDING = 'pending', 'قيد الإرسال'
        SENT = 'sent', 'تم الإرسال'
        FAILED = 'failed', 'فشل مؤقت'
        RETRYING = 'retrying', 'إعادة محاولة'
        GIVEN_UP = 'given_up', 'تم التخلي بعد استنفاد المحاولات'

    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='deliveries')
    channel = models.CharField(max_length=10, choices=Channel.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)

    # مصيَّران مرة واحدة وقت إنشاء الإشعار (نفس مبدأ in_app) — تعديل القالب لاحقاً لا يغيّر رسائل جاهزة للإرسال.
    rendered_subject = models.CharField(max_length=255, blank=True, default='')
    rendered_body = models.TextField(blank=True, default='')

    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    provider_message_id = models.CharField(max_length=255, blank=True, default='')

    # حتمي عند الإنشاء: f"{notification_id}:{channel}" — يمنع صف تسليم مكرر لنفس (إشعار، قناة) على مستوى القاعدة.
    idempotency_key = models.CharField(max_length=64, unique=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'NotificationDelivery'
        indexes = [
            models.Index(fields=['status', 'channel'], name='notifdlv_status_channel_idx'),
        ]

    def __str__(self):
        return f"{self.channel}:{self.status} for notification {self.notification_id}"


class NotificationTemplate(models.Model):
    """قوالب نصية لكل (نوع إشعار × قناة × لغة). تُصيَّر مرة واحدة وقت الإنشاء وتُخزَّن في Notification —
    تعديل القالب لاحقاً لا يغيّر إشعارات صدرت سابقاً."""

    CHANNEL_CHOICES = [
        ('in_app', 'داخل التطبيق'),
        ('email', 'بريد إلكتروني'),
        ('push', 'إشعار جوال'),
    ]

    notification_type = models.CharField(
        max_length=40, choices=Notification.NotificationType.choices, db_index=True,
    )
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    language = models.CharField(max_length=5, default='ar')  # يطابق User.preferred_language ('ar'/'en')

    subject_template = models.CharField(max_length=255, blank=True, default='')
    body_template = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'NotificationTemplate'
        unique_together = ('notification_type', 'channel', 'language')

    def __str__(self):
        return f"{self.notification_type}/{self.channel}/{self.language}"


class UserNotificationPreference(models.Model):
    """صف واحد فقط لكل (مستخدم × نوع إشعار) عند التخصيص الفعلي — لا صفوف افتراضية عند التسجيل.
    غياب الصف يعني استخدام DEFAULT_CHANNELS_BY_TYPE في notifications/services.py."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_preferences',
    )
    notification_type = models.CharField(max_length=40, choices=Notification.NotificationType.choices)

    in_app_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=False)  # اختياري: لا يوجد تطبيق جوال بعد

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'UserNotificationPreference'
        unique_together = ('user', 'notification_type')

    def __str__(self):
        return f"{self.user_id}:{self.notification_type}"


class DeviceToken(models.Model):
    """رموز أجهزة لإشعارات الجوال (Phase 5) — عند إبلاغ FCM أن الرمز غير صالح يُعطَّل لا يُحذف،
    نفس نمط PasswordResetToken.is_used في accounts."""

    PLATFORM_CHOICES = [
        ('android', 'Android'),
        ('ios', 'iOS'),
        ('web', 'Web'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='device_tokens')
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'DeviceToken'
        indexes = [
            models.Index(fields=['user', 'is_active'], name='devicetoken_user_active_idx'),
        ]

    def __str__(self):
        return f"{self.platform} token for {self.user_id}"
