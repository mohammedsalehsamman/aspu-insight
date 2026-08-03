import logging
from datetime import timedelta
from smtplib import SMTPException

from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from firebase_admin.exceptions import FirebaseError
from firebase_admin.messaging import UnregisteredError

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


def _get_firebase_app():
    import firebase_admin
    from firebase_admin import credentials

    try:
        return firebase_admin.get_app()
    except ValueError:
        return firebase_admin.initialize_app(credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH))


@shared_task(autoretry_for=(FirebaseError,), retry_backoff=True, retry_backoff_max=600, max_retries=5)
def send_push_notification(delivery_id):
    """يرسل عبر Firebase Cloud Messaging (HTTP v1) — تصميم استشرافي (Phase 5)، لا تطبيق
    جوال فعلي يستهلكه اليوم فلا يمكن اختباره من طرف-إلى-طرف؛ يُختبَر بمحاكاة استدعاء FCM فقط.
    بلا FIREBASE_CREDENTIALS_PATH: يتخلّى فوراً (GIVEN_UP) دون أي محاولة اتصال. UnregisteredError
    (الرمز لم يعد صالحاً) ليست ضمن autoretry_for عمداً — تُعامَل كفشل نهائي أدناه، لا مؤقت."""
    try:
        delivery = NotificationDelivery.objects.select_related('device_token').get(pk=delivery_id)
    except NotificationDelivery.DoesNotExist:
        logger.warning("NotificationDelivery %s not found; skipping push.", delivery_id)
        return
    if delivery.status == NotificationDelivery.Status.SENT:
        return  # ضمان عدم التكرار الحقيقي (DB) — نفس مبدأ send_email_notification

    if not settings.FIREBASE_CREDENTIALS_PATH:
        delivery.status = NotificationDelivery.Status.GIVEN_UP
        delivery.error_message = 'FIREBASE_CREDENTIALS_PATH غير مضبوط.'
        delivery.save(update_fields=['status', 'error_message'])
        return

    from firebase_admin import messaging

    delivery.attempt_count += 1
    delivery.last_attempted_at = timezone.now()
    message = messaging.Message(
        notification=messaging.Notification(title=delivery.rendered_subject, body=delivery.rendered_body),
        data={'notification_id': str(delivery.notification_id)},
        token=delivery.device_token.token,
    )
    try:
        _get_firebase_app()
        provider_message_id = messaging.send(message)
    except UnregisteredError as exc:
        # الرمز لم يعد صالحاً على جهاز المستخدم — يُعطَّل لا يُحذف (نفس نمط PasswordResetToken.is_used).
        delivery.device_token.is_active = False
        delivery.device_token.save(update_fields=['is_active'])
        delivery.status = NotificationDelivery.Status.GIVEN_UP
        delivery.error_message = f"رمز غير مسجَّل، عُطِّل الجهاز: {exc}"
        delivery.save(update_fields=['attempt_count', 'last_attempted_at', 'status', 'error_message'])
        return
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
    delivery.provider_message_id = provider_message_id
    delivery.save(update_fields=['attempt_count', 'last_attempted_at', 'status', 'sent_at', 'provider_message_id'])


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


@shared_task
def send_daily_notification_digest():
    """ملخص بريدي اختياري (Phase 6) — إشعار واحد مجمَّع بدل مضايقة المستخدم بعدد كبير من
    رسائل فردية. لا يمرّ عبر NotificationDelivery/NotificationTemplate (ليس نوع إشعار،
    بل تلخيص عبر البريد مباشرة)، ولا يتأثر بتفضيل email لكل نوع — قرار تبسيط متعمَّد؛
    أول من يستفيد فعلياً حين يبني تطبيق الجوال مستقبلاً هو من يستحق ضبطاً أدق لهذا التمييز."""
    from django.contrib.auth import get_user_model
    from notifications.models import Notification

    User = get_user_model()
    since = timezone.now() - timedelta(days=1)

    recipient_ids = (
        Notification.objects.filter(created_at__gte=since, is_read=False)
        .values_list('recipient_id', flat=True).distinct()
    )
    sent = 0
    for user in User.objects.filter(pk__in=recipient_ids, is_active=True):
        unread = Notification.objects.filter(
            recipient=user, created_at__gte=since, is_read=False,
        ).order_by('-created_at')
        lines = [f"- {n.title}" for n in unread[:20]]
        body = "لديك {} إشعاراً جديداً خلال آخر 24 ساعة:\n\n{}\n\nفريق ASPU Insight".format(
            unread.count(), "\n".join(lines),
        )
        send_mail(
            subject='ملخص إشعاراتك اليومي - ASPU Insight',
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
        sent += 1
    return sent


@shared_task
def cleanup_old_read_notifications(retention_days=90):
    """تنظيف دوري (Phase 6) — الإشعارات المقروءة الأقدم من retention_days تُحذف نهائياً
    (لا تعطيل/أرشفة: هي سجل تنبيه مقروء بالفعل، على عكس ResearchHistory الذي هو سجل تدقيق
    دائم). لا يمسّ NotificationDelivery المرتبط (CASCADE مع Notification نفسه)."""
    from notifications.models import Notification

    cutoff = timezone.now() - timedelta(days=retention_days)
    deleted_count, _ = Notification.objects.filter(is_read=True, read_at__lt=cutoff).delete()
    return deleted_count
