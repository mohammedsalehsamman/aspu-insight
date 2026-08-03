"""قواعد تحويل حدث تغيّر حالة البحث (ResearchHistory) إلى نوع إشعار.

مفصولة عن notifications/signals.py لتسهيل اختبارها بمعزل عن الإشارات نفسها.
"""
from research.models import ResearchPaper

# فقط الحالات ذات المعنى للمستخدم تُشعِر — نتفادى إزعاج المستخدمين بحالات الأنابيب
# الآلية العابرة مثل CHECKING_PLAGIARISM.
NOTIFIABLE_STATUSES = {
    ResearchPaper.Status.SUBMITTED,
    ResearchPaper.Status.EDITOR_REVIEW,
    ResearchPaper.Status.REVISION_REQUIRED,
    ResearchPaper.Status.COMMITTEE_REVIEW,
    ResearchPaper.Status.ACCEPTED,
    ResearchPaper.Status.REJECTED,
    ResearchPaper.Status.PLAGIARISM_FAILED,
    ResearchPaper.Status.PUBLISHED,
}


def resolve_type(history):
    """يحدد نوع الإشعار المناسب انطلاقاً من حالة الانتقال ودور من قام به.

    history: نسخة ResearchHistory تم إنشاؤها للتو (created=True).
    """
    from notifications.models import Notification

    if history.to_status == ResearchPaper.Status.PUBLISHED:
        return Notification.NotificationType.PAPER_PUBLISHED

    role = getattr(history.changed_by, 'role', None)
    if role == 'assistant_editor':
        return Notification.NotificationType.ASSISTANT_REVIEW_RECEIVED
    if role == 'editor':
        return Notification.NotificationType.EDITOR_REVIEW_RECEIVED
    if history.to_status == ResearchPaper.Status.SUBMITTED:
        return Notification.NotificationType.PAPER_SUBMITTED

    return Notification.NotificationType.PAPER_STATUS_CHANGED
