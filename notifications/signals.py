"""نقاط الربط المبنية على الإشارات (Signal-based hook points).

تُستخدم فقط حيث توجد نقطة ربط آمنة من التكرار:
- ResearchHistory: سجل append-only لا يُعاد حفظه أبداً بعد إنشائه (تم التحقق من
  researchHistory/services.py وكل مواقع الاستدعاء) — لذا post_save عليه، مقيّداً
  بـ created=True، لا يخاطر بأي تكرار.
- User: نقطة الإشارة الوحيدة الموجودة أصلاً في هذا الكود (accounts/signals.py، كانت
  no-op) — تمديدها لرصد تغيّر role أكثر اتساقاً من التدخل داخل DRF generic mixins.

لا يوجد post_save على ResearchPaper نفسه عمداً: أي أثر جانبي للإشعار يجب ألا يخاطر
بإعادة دخول paper.save() (مشكلة Signal Recursion).
"""
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from notifications.models import Notification
from notifications.rules import NOTIFIABLE_STATUSES, resolve_type
from notifications.services import NotificationService
from researchHistory.models import ResearchHistory

User = get_user_model()


@receiver(post_save, sender=ResearchHistory)
def notify_on_paper_status_change(sender, instance, created, **kwargs):
    if not created or instance.to_status not in NOTIFIABLE_STATUSES:
        return

    paper = instance.paper
    notification_type = resolve_type(instance)
    actor_id = getattr(instance.changed_by, 'user_id', None)

    recipients = {paper.author}
    if notification_type == Notification.NotificationType.PAPER_SUBMITTED:
        recipients |= set(User.objects.filter(role='assistant_editor'))
    elif paper.assigned_editor_id:
        recipients.add(paper.assigned_editor)

    for user in recipients:
        if user is None or user.user_id == actor_id:
            continue  # لا نُشعر الفاعل بنتيجة فعله هو نفسه
        NotificationService.create_notification(
            recipient=user,
            notification_type=notification_type,
            actor=instance.changed_by,
            target=paper,
            target_repr=paper.title,
            level=Notification.Level.SUCCESS if paper.status == 'published' else Notification.Level.INFO,
            context={
                'paper_title': paper.title,
                'from_status': instance.from_status,
                'to_status': instance.to_status,
                'note': instance.note,
                'fallback_title': f"تحديث حالة البحث: {paper.title}",
                'fallback_body': f"تغيّرت حالة البحث من {instance.from_status} إلى {instance.to_status}.",
            },
        )


@receiver(pre_save, sender=User)
def stash_previous_role(sender, instance, **kwargs):
    instance._previous_role = (
        User.objects.filter(pk=instance.pk).values_list('role', flat=True).first()
        if instance.pk else None
    )


@receiver(post_save, sender=User)
def notify_on_role_change(sender, instance, created, **kwargs):
    previous_role = getattr(instance, '_previous_role', None)
    if created or previous_role is None or previous_role == instance.role:
        return

    NotificationService.create_notification(
        recipient=instance,
        notification_type=Notification.NotificationType.ROLE_CHANGED,
        target=instance,
        target_repr=instance.full_name,
        level=Notification.Level.WARNING,
        context={
            'old_role': previous_role,
            'new_role': instance.role,
            'fallback_title': 'تغيّرت صلاحيتك في المنصة',
            'fallback_body': f"تم تغيير صلاحيتك من {previous_role} إلى {instance.role}.",
        },
    )
