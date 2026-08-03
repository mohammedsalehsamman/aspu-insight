"""مفاتيح واستدعاءات Cache المشتركة لتطبيق notifications.

يستخدم CACHES['default'] القياسي في settings.py (LocMemCache محلياً بلا Redis، أو
django-redis فور ضبط REDIS_URL) — لا عميل Redis منفصل، تجنباً لازدواج آلية الاتصال.
"""
from django.core.cache import cache

# شبكة أمان فقط لعدّاد غير المقروء — الإبطال الصريح عند كل كتابة (mark_read/mark_all_read/
# create_notification) هو مصدر الصحة الفعلي، وليس انتهاء الصلاحية. راجع القرار في خطة الإشعارات.
UNREAD_COUNT_TIMEOUT = 300

# تذكرة اتصال WebSocket أحادية الاستخدام — عمر قصير عمداً (راجع NotificationWSTicketAPIView).
WS_TICKET_TIMEOUT = 30


def unread_count_cache_key(user_id):
    return f"notif:unread:{user_id}"


def invalidate_unread_count(user_id):
    cache.delete(unread_count_cache_key(user_id))


def ws_ticket_cache_key(ticket):
    return f"ws_ticket:{ticket}"
