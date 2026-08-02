import secrets

from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.cache import (
    UNREAD_COUNT_TIMEOUT,
    WS_TICKET_TIMEOUT,
    invalidate_unread_count,
    unread_count_cache_key,
    ws_ticket_cache_key,
)
from notifications.models import DeviceToken, Notification, UserNotificationPreference
from notifications.serializers import (
    DeviceTokenSerializer,
    NotificationPreferenceSerializer,
    NotificationSerializer,
)
from notifications.services import NON_DISABLEABLE_IN_APP, NotificationService


class NotificationListAPIView(generics.ListAPIView):
    """قائمة إشعارات المستخدم الحالي فقط — لا يُقبل أبداً معرّف مستخدم من مدخلات العميل."""

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_read', 'notification_type']

    def get_queryset(self):
        return (
            Notification.objects
            .filter(recipient=self.request.user)
            .select_related('actor', 'target_content_type')
        )


class NotificationGroupedListAPIView(APIView):
    """تجميع وقت القراءة عبر group_key (Phase 6) — كل حدث يبقى صفاً مستقلاً في Notification
    (لا دمج وقت الكتابة، راجع القرار في خطة الإشعارات)؛ هذه النقطة فقط تعرض لكل مجموعة أحدث
    إشعار فيها + عدد إشعاراتها الكلي وغير المقروء. group_key الفارغ (لا نوع/هدف مشترك حقيقي)
    يُستبعَد من التجميع."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        groups = (
            Notification.objects
            .filter(recipient=request.user)
            .exclude(group_key='')
            .values('group_key')
            .annotate(latest_id=Max('id'), count=Count('id'), unread_count=Count('id', filter=Q(is_read=False)))
        )
        counts_by_latest_id = {row['latest_id']: row for row in groups}

        notifications = (
            Notification.objects
            .filter(id__in=counts_by_latest_id.keys())
            .select_related('actor', 'target_content_type')
        )
        results = []
        for notification in notifications:
            row = counts_by_latest_id[notification.id]
            data = NotificationSerializer(notification).data
            data['count'] = row['count']
            data['unread_count'] = row['unread_count']
            results.append(data)

        results.sort(key=lambda d: d['created_at'], reverse=True)
        return Response(results)


class NotificationUnreadCountAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        key = unread_count_cache_key(request.user.pk)
        count = cache.get(key)
        if count is None:
            count = Notification.objects.filter(recipient=request.user, is_read=False).count()
            cache.set(key, count, UNREAD_COUNT_TIMEOUT)
        return Response({'unread_count': count})


class NotificationMarkReadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
        notification.mark_read()
        return Response(NotificationSerializer(notification).data)


class NotificationMarkAllReadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        updated = Notification.objects.filter(recipient=request.user, is_read=False).update(
            is_read=True, read_at=timezone.now(),
        )
        transaction.on_commit(lambda: invalidate_unread_count(request.user.pk))
        return Response({'updated': updated}, status=status.HTTP_200_OK)


class NotificationPreferenceAPIView(APIView):
    """تفضيلات المستخدم الحالي لكل (نوع إشعار × قناة).

    القراءة تُرجع القيمة الفعّالة لكل الأنواع (افتراضي أو مخصَّص) دون إنشاء أي صف؛ الكتابة
    تُنشئ/تُحدّث صفاً فقط للأنواع المُرسَلة فعلياً — لا صفوف افتراضية تُزرع لمجرد القراءة
    (نفس مبدأ UserNotificationPreference الموثَّق في notifications/models.py).
    """

    permission_classes = [IsAuthenticated]

    @staticmethod
    def _serialize(notification_type, channels):
        return {
            'notification_type': notification_type,
            'non_disableable': notification_type in NON_DISABLEABLE_IN_APP,
            'in_app_enabled': channels['in_app'],
            'email_enabled': channels['email'],
            'push_enabled': channels['push'],
        }

    def get(self, request):
        data = [
            self._serialize(value, NotificationService._resolve_channels(request.user, value))
            for value, _ in Notification.NotificationType.choices
        ]
        return Response(data)

    def patch(self, request):
        serializer = NotificationPreferenceSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        results = []
        for item in serializer.validated_data:
            notification_type = item['notification_type']
            current = NotificationService._resolve_channels(request.user, notification_type)
            preference, _ = UserNotificationPreference.objects.update_or_create(
                user=request.user,
                notification_type=notification_type,
                defaults={
                    'in_app_enabled': item.get('in_app_enabled', current['in_app']),
                    'email_enabled': item.get('email_enabled', current['email']),
                    'push_enabled': item.get('push_enabled', current['push']),
                },
            )
            results.append(self._serialize(notification_type, {
                'in_app': preference.in_app_enabled,
                'email': preference.email_enabled,
                'push': preference.push_enabled,
            }))
        return Response(results)


class NotificationWSTicketAPIView(APIView):
    """يصدر تذكرة اتصال WebSocket أحادية الاستخدام قصيرة الأجل (٣٠ ثانية)، بدل تمرير JWT
    كامل الصلاحية داخل رابط wss://‎ حيث يظهر في سجلات الخوادم الوسيطة والمتصفح. العميل يفتح
    الاتصال بـ ws(s)://.../ws/notifications/?ticket=<ticket> فور استلامها.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        ticket = secrets.token_urlsafe(32)
        cache.set(ws_ticket_cache_key(ticket), request.user.pk, WS_TICKET_TIMEOUT)
        return Response({'ticket': ticket, 'expires_in': WS_TICKET_TIMEOUT})


class DeviceTokenAPIView(APIView):
    """تسجيل/إلغاء رمز جهاز لإشعارات push — Phase 5 (تصميم استشرافي، لا تطبيق جوال فعلي
    يستهلكها اليوم). التسجيل يُعيد ربط الرمز بالمستخدم الحالي دوماً (update_or_create) — نفس
    جهاز الجوال قد يُستخدم من حساب آخر لاحقاً (تسجيل خروج/دخول)، والرمز نفسه لا يتغيّر."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        device_token, _ = DeviceToken.objects.update_or_create(
            token=serializer.validated_data['token'],
            defaults={
                'user': request.user,
                'platform': serializer.validated_data['platform'],
                'is_active': True,
                'last_used_at': timezone.now(),
            },
        )
        return Response(DeviceTokenSerializer(device_token).data, status=status.HTTP_201_CREATED)

    def delete(self, request):
        token = request.data.get('token')
        if not token:
            return Response({'detail': 'token مطلوب.'}, status=status.HTTP_400_BAD_REQUEST)

        deleted, _ = DeviceToken.objects.filter(user=request.user, token=token).delete()
        if not deleted:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
