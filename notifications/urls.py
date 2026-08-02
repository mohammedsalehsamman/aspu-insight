from django.urls import path

from notifications.views import (
    DeviceTokenAPIView,
    NotificationListAPIView,
    NotificationGroupedListAPIView,
    NotificationUnreadCountAPIView,
    NotificationMarkReadAPIView,
    NotificationMarkAllReadAPIView,
    NotificationPreferenceAPIView,
    NotificationWSTicketAPIView,
)

urlpatterns = [
    path('', NotificationListAPIView.as_view(), name='notification-list'),
    path('grouped/', NotificationGroupedListAPIView.as_view(), name='notification-grouped-list'),
    path('unread-count/', NotificationUnreadCountAPIView.as_view(), name='notification-unread-count'),
    path('<int:pk>/read/', NotificationMarkReadAPIView.as_view(), name='notification-mark-read'),
    path('mark-all-read/', NotificationMarkAllReadAPIView.as_view(), name='notification-mark-all-read'),
    path('preferences/', NotificationPreferenceAPIView.as_view(), name='notification-preferences'),
    path('ws-ticket/', NotificationWSTicketAPIView.as_view(), name='notification-ws-ticket'),
    path('device-tokens/', DeviceTokenAPIView.as_view(), name='notification-device-tokens'),
]
