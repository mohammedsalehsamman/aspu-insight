"""مستهلك WebSocket لدفع نبضة "يوجد جديد" فقط — لا محتوى كامل، REST يبقى مصدر الحقيقة الوحيد
(العميل يعيد الجلب عبر GET /notifications/ و/notifications/unread-count/ دوماً). راجع
notifications/tasks.py: push_ws_notification لمصدر النبضة.

المصادقة عبر تذكرة أحادية الاستخدام قصيرة الأجل (لا JWT كامل الصلاحية في query string يظهر في
سجلات الخوادم الوسيطة) — راجع notifications/views.py: NotificationWSTicketAPIView لإصدارها.
"""
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.cache import cache

from notifications.cache import ws_ticket_cache_key


def _consume_ticket(ticket):
    key = ws_ticket_cache_key(ticket)
    user_id = cache.get(key)
    if user_id is not None:
        cache.delete(key)  # أحادية الاستخدام — لا get_or_set إعادة استخدام لاحقة
    return user_id


class NotificationConsumer(AsyncJsonWebsocketConsumer):

    async def connect(self):
        query = parse_qs(self.scope['query_string'].decode())
        ticket = query.get('ticket', [None])[0]
        user_id = await sync_to_async(_consume_ticket)(ticket) if ticket else None

        if user_id is None:
            await self.close(code=4001)
            return

        self.group_name = f"notifications_user_{user_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if getattr(self, 'group_name', None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_new(self, event):
        """يستقبل group_send بـ type='notification.new' من push_ws_notification."""
        await self.send_json({
            'type': 'notification.new',
            'notification_id': event['notification_id'],
            'unread_count': event['unread_count'],
        })
