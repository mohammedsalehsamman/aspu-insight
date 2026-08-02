"""نقطة الكتابة الوحيدة لإنشاء الإشعارات — كل نقاط الربط (إشارات أو نداءات صريحة)
تمر عبر NotificationService.create_notification فقط.

Phase 1: يُنشئ صف Notification (in_app) فقط. من Phase 2/5 سيُستدعى هنا أيضاً إنشاء
NotificationDelivery لكل قناة خارجية مفعّلة واستدعاء مهام Celery المقابلة عبر
transaction.on_commit، دون تغيير في توقيع create_notification.
"""
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.template import Context, Template

from notifications.models import (
    Notification,
    NotificationDelivery,
    NotificationTemplate,
    UserNotificationPreference,
)

# الافتراضي لأي نوع غير مذكور هنا: in_app فقط (email/push معطّلان).
DEFAULT_CHANNELS_BY_TYPE = {
    Notification.NotificationType.PAPER_SUBMITTED: {'in_app': True, 'email': False, 'push': False},
    Notification.NotificationType.PAPER_STATUS_CHANGED: {'in_app': True, 'email': False, 'push': False},
    Notification.NotificationType.PAPER_PUBLISHED: {'in_app': True, 'email': True, 'push': False},
    Notification.NotificationType.ASSISTANT_REVIEW_RECEIVED: {'in_app': True, 'email': False, 'push': False},
    Notification.NotificationType.EDITOR_REVIEW_RECEIVED: {'in_app': True, 'email': False, 'push': False},
    Notification.NotificationType.COMMITTEE_REVIEW_RECEIVED: {'in_app': True, 'email': True, 'push': False},
    Notification.NotificationType.COMMITTEE_DEADLINE_APPROACHING: {'in_app': True, 'email': True, 'push': False},
    Notification.NotificationType.COMMITTEE_DEADLINE_EXPIRED: {'in_app': True, 'email': True, 'push': False},
    Notification.NotificationType.EDITOR_ASSIGNED: {'in_app': True, 'email': False, 'push': False},
    Notification.NotificationType.REVIEWER_ASSIGNED_TO_COMMITTEE: {'in_app': True, 'email': True, 'push': False},
    Notification.NotificationType.ROLE_CHANGED: {'in_app': True, 'email': False, 'push': False},
    Notification.NotificationType.SYSTEM_ANNOUNCEMENT: {'in_app': True, 'email': True, 'push': False},
    Notification.NotificationType.DISCUSSION_MENTION: {'in_app': True, 'email': False, 'push': False},
    Notification.NotificationType.ISSUE_PUBLISHED: {'in_app': True, 'email': True, 'push': False},
}

# هذه الأنواع حرجة بما يكفي ليُفرض in_app=True دائماً بغض النظر عن تفضيل المستخدم.
NON_DISABLEABLE_IN_APP = {
    Notification.NotificationType.ROLE_CHANGED,
    Notification.NotificationType.COMMITTEE_DEADLINE_EXPIRED,
    Notification.NotificationType.SYSTEM_ANNOUNCEMENT,
}


class NotificationService:

    @staticmethod
    def _resolve_channels(user, notification_type):
        defaults = DEFAULT_CHANNELS_BY_TYPE.get(
            notification_type, {'in_app': True, 'email': False, 'push': False},
        )
        override = UserNotificationPreference.objects.filter(
            user=user, notification_type=notification_type,
        ).first()
        channels = defaults if not override else {
            'in_app': override.in_app_enabled,
            'email': override.email_enabled,
            'push': override.push_enabled,
        }
        if notification_type in NON_DISABLEABLE_IN_APP:
            channels = {**channels, 'in_app': True}
        return channels

    @staticmethod
    def _render(notification_type, channel, language, context):
        template = (
            NotificationTemplate.objects.filter(
                notification_type=notification_type, channel=channel, language=language, is_active=True,
            ).first()
            or NotificationTemplate.objects.filter(
                notification_type=notification_type, channel=channel, language='ar', is_active=True,
            ).first()
        )
        if not template:
            return context.get('fallback_title', ''), context.get('fallback_body', '')

        rendered_context = Context(context)
        subject = Template(template.subject_template).render(rendered_context) if template.subject_template else ''
        body = Template(template.body_template).render(rendered_context)
        return subject, body

    @staticmethod
    @transaction.atomic
    def create_notification(*, recipient, notification_type, target=None, actor=None,
                             level=Notification.Level.INFO, context=None, target_repr=''):
        """ينشئ إشعاراً واحداً لمستلم واحد، إن كانت قناة in_app مفعّلة له لهذا النوع.

        يُعيد نسخة Notification المُنشأة، أو None إن كان المستخدم قد عطّل in_app لهذا النوع.
        """
        context = context or {}
        channels = NotificationService._resolve_channels(recipient, notification_type)
        if not channels['in_app']:
            return None

        language = getattr(recipient, 'preferred_language', 'ar') or 'ar'
        title, body = NotificationService._render(notification_type, 'in_app', language, context)

        content_type = ContentType.objects.get_for_model(target) if target is not None else None
        target_id = target.pk if target is not None else None

        notification = Notification.objects.create(
            recipient=recipient,
            actor=actor,
            notification_type=notification_type,
            level=level,
            title=title,
            body=body,
            data=context,
            target_content_type=content_type,
            target_object_id=target_id,
            target_repr=target_repr,
            group_key=f"{notification_type}:{content_type.id if content_type else 0}:{target_id or 0}",
        )

        if channels['email']:
            subject, body = NotificationService._render(notification_type, 'email', language, context)
            delivery = NotificationDelivery.objects.create(
                notification=notification,
                channel=NotificationDelivery.Channel.EMAIL,
                rendered_subject=subject,
                rendered_body=body,
                idempotency_key=f"{notification.id}:email",
            )
            # استيراد متأخر لتفادي استيراد دائري بين services.py وtasks.py
            from notifications.tasks import send_email_notification
            transaction.on_commit(lambda: send_email_notification.delay(delivery.id))

        # Phase 5: نفس المنطق لقناة push (DeviceToken + send_push_notification) يُضاف هنا لاحقاً.
        return notification
