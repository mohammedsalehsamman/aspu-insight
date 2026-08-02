from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.models import Notification, UserNotificationPreference
from notifications.serializers import NotificationPreferenceSerializer, NotificationSerializer
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


class NotificationUnreadCountAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
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
