"""نقطة الكتابة الوحيدة لإنشاء الإشعارات — كل نقاط الربط (إشارات أو نداءات صريحة)
تمر عبر NotificationService.create_notification فقط.

create_notification ينشئ صف Notification (in_app)، ثم عبر transaction.on_commit فقط
(لا شيء يُطلَق قبل نجاح المعاملة): NotificationDelivery + send_email_notification إن
كانت قناة email مفعّلة، NotificationDelivery لكل جهاز نشط + send_push_notification إن
كانت قناة push مفعّلة، إبطال Cache عدّاد غير المقروء، ودفع نبضة push_ws_notification
عبر WebSocket.
"""
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.template import Context, Template

from notifications.models import (
    DeviceToken,
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

        if channels['push']:
            push_title, push_body = NotificationService._render(notification_type, 'push', language, context)
            # جهاز واحد = صف تسليم واحد — لا "مستلم واحد" كالبريد؛ نفس المستخدم قد يملك عدة
            # أجهزة (أندرويد + iOS + ويب) وكلها يجب أن تستلم النبضة نفسها.
            for device_token in DeviceToken.objects.filter(user=recipient, is_active=True):
                delivery = NotificationDelivery.objects.create(
                    notification=notification,
                    channel=NotificationDelivery.Channel.PUSH,
                    device_token=device_token,
                    rendered_subject=push_title,
                    rendered_body=push_body,
                    idempotency_key=f"{notification.id}:push:{device_token.id}",
                )
                from notifications.tasks import send_push_notification
                # d_id مُلزَم كقيمة افتراضية للوسيطة — لا اعتماد على إغلاق المتغيّر device_token/delivery
                # عبر التكرار (وإلا لاستخدمت كل الاستدعاءات المؤجَّلة قيمة delivery الأخيرة في الحلقة).
                transaction.on_commit(lambda d_id=delivery.id: send_push_notification.delay(d_id))

        # الإبطال ودفع WebSocket مؤجَّلان لِما بعد نجاح الـ commit — تراجع المعاملة يجب ألا
        # يُطلق أي أثر خارجي (نفس المبدأ المطبَّق على البريد وpush أعلاه).
        from notifications.cache import invalidate_unread_count
        from notifications.tasks import push_ws_notification
        transaction.on_commit(lambda: invalidate_unread_count(recipient.pk))
        transaction.on_commit(lambda: push_ws_notification.delay(notification.id))

        return notification
