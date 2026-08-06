from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.test import SimpleTestCase

from notifications.cache import ws_ticket_cache_key
from notifications.consumers import NotificationConsumer


class NotificationConsumerTest(SimpleTestCase):
    """يختبر NotificationConsumer مباشرة (WebsocketCommunicator، بلا خادم فعلي) — يطابق طبقة
    القنوات في-الذاكرة المُستخدَمة محلياً افتراضياً بلا REDIS_URL (راجع aspu_insight/settings.py)."""

    def setUp(self):
        cache.clear()

    async def test_valid_ticket_connects_and_joins_group(self):
        cache.set(ws_ticket_cache_key('good-ticket'), 42, 30)
        communicator = WebsocketCommunicator(NotificationConsumer.as_asgi(), '/ws/notifications/?ticket=good-ticket')

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        await communicator.disconnect()

    async def test_ticket_is_single_use(self):
        cache.set(ws_ticket_cache_key('one-shot'), 42, 30)
        communicator = WebsocketCommunicator(NotificationConsumer.as_asgi(), '/ws/notifications/?ticket=one-shot')

        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        self.assertIsNone(cache.get(ws_ticket_cache_key('one-shot')))

        await communicator.disconnect()

    async def test_reused_ticket_is_rejected_on_second_connection_attempt(self):
        cache.set(ws_ticket_cache_key('reuse-me'), 42, 30)
        first = WebsocketCommunicator(NotificationConsumer.as_asgi(), '/ws/notifications/?ticket=reuse-me')
        connected, _ = await first.connect()
        self.assertTrue(connected)
        await first.disconnect()

        second = WebsocketCommunicator(NotificationConsumer.as_asgi(), '/ws/notifications/?ticket=reuse-me')
        connected, close_code = await second.connect()

        self.assertFalse(connected)
        self.assertEqual(close_code, 4001)

    async def test_missing_ticket_closes_with_4001(self):
        communicator = WebsocketCommunicator(NotificationConsumer.as_asgi(), '/ws/notifications/')

        connected, close_code = await communicator.connect()

        self.assertFalse(connected)
        self.assertEqual(close_code, 4001)

    async def test_unknown_or_expired_ticket_closes_with_4001(self):
        communicator = WebsocketCommunicator(
            NotificationConsumer.as_asgi(), '/ws/notifications/?ticket=does-not-exist',
        )

        connected, close_code = await communicator.connect()

        self.assertFalse(connected)
        self.assertEqual(close_code, 4001)

    async def test_receives_pushed_notification_event(self):
        cache.set(ws_ticket_cache_key('push-ticket'), 99, 30)
        communicator = WebsocketCommunicator(NotificationConsumer.as_asgi(), '/ws/notifications/?ticket=push-ticket')
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        channel_layer = get_channel_layer()
        await channel_layer.group_send('notifications_user_99', {
            'type': 'notification.new',
            'notification_id': 7,
            'unread_count': 3,
        })

        message = await communicator.receive_json_from()
        self.assertEqual(message, {'type': 'notification.new', 'notification_id': 7, 'unread_count': 3})

        await communicator.disconnect()
