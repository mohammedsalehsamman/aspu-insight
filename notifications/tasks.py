import logging
from datetime import timedelta
from smtplib import SMTPException

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from notifications.models import NotificationDelivery

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(SMTPException, ConnectionError),
             retry_backoff=True, retry_backoff_max=600, max_retries=5)
def send_email_notification(self, delivery_id):
    try:
        delivery = NotificationDelivery.objects.select_related('notification__recipient').get(pk=delivery_id)
    except NotificationDelivery.DoesNotExist:
        logger.warning("NotificationDelivery %s not found; skipping.", delivery_id)
        return
    if delivery.status == NotificationDelivery.Status.SENT:
        return  # ضمان عدم التكرار الحقيقي (DB) — راجع القرار في خطة الإشعارات

    delivery.attempt_count += 1
    delivery.last_attempted_at = timezone.now()
    try:
        send_mail(
            subject=delivery.rendered_subject,
            message=delivery.rendered_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[delivery.notification.recipient.email],
            fail_silently=False,
        )
    except Exception as exc:
        delivery.status = (
            NotificationDelivery.Status.GIVEN_UP
            if delivery.attempt_count >= delivery.max_attempts
            else NotificationDelivery.Status.RETRYING
        )
        delivery.error_message = str(exc)
        delivery.save(update_fields=['attempt_count', 'last_attempted_at', 'status', 'error_message'])
        raise

    delivery.status = NotificationDelivery.Status.SENT
    delivery.sent_at = timezone.now()
    delivery.save(update_fields=['attempt_count', 'last_attempted_at', 'status', 'sent_at'])


@shared_task
def push_ws_notification(notification_id):
    """يدفع نبضة فقط (لا محتوى كامل) لمجموعة WebSocket الخاصة بمستلم الإشعار — العميل
    يعيد الجلب دوماً عبر REST (راجع notifications/consumers.py). لا تأثير إن كانت طبقة
    القنوات في-الذاكرة محلياً (بلا REDIS_URL): group_send لا يفشل، فقط لا يصل لأي مستهلك
    خارج نفس العملية."""
    from notifications.models import Notification

    try:
        notification = Notification.objects.get(pk=notification_id)
    except Notification.DoesNotExist:
        logger.warning("Notification %s not found; skipping WS push.", notification_id)
        return

    unread_count = Notification.objects.filter(recipient_id=notification.recipient_id, is_read=False).count()
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"notifications_user_{notification.recipient_id}",
        {
            'type': 'notification.new',
            'notification_id': notification.id,
            'unread_count': unread_count,
        },
    )


@shared_task
def check_committee_deadlines_approaching():
    from django.contrib.contenttypes.models import ContentType

    from committees.models import Committee
    from notifications.models import Notification
    from notifications.services import NotificationService

    now = timezone.now()
    soon = now + timedelta(days=3)
    upcoming = Committee.objects.filter(
        deadline__lte=soon, deadline__gt=now, status__in=['pending', 'approved'],
    ).select_related('editor', 'paper')

    # يطابق تماماً الصيغة التي يحسبها NotificationService.create_notification لضمان تطابق التكرار.
    committee_content_type_id = ContentType.objects.get_for_model(Committee).id

    for committee in upcoming:
        group_key = (
            f"{Notification.NotificationType.COMMITTEE_DEADLINE_APPROACHING}:"
            f"{committee_content_type_id}:{committee.id}"
        )
        already_sent_today = Notification.objects.filter(
            group_key=group_key, created_at__date=now.date(),
        ).exists()
        if already_sent_today:
            continue
        NotificationService.create_notification(
            recipient=committee.editor,
            notification_type=Notification.NotificationType.COMMITTEE_DEADLINE_APPROACHING,
            target=committee,
            target_repr=committee.paper.title,
            level=Notification.Level.WARNING,
            context={
                'paper_title': committee.paper.title,
                'deadline': committee.deadline.isoformat(),
                'fallback_title': 'اقتراب موعد اللجنة',
                'fallback_body': f"يقترب الموعد النهائي للجنة تحكيم البحث: {committee.paper.title}",
            },
        )
