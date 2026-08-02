from django.urls import path

from notifications.views import (
    NotificationListAPIView,
    NotificationUnreadCountAPIView,
    NotificationMarkReadAPIView,
    NotificationMarkAllReadAPIView,
    NotificationPreferenceAPIView,
)

urlpatterns = [
    path('', NotificationListAPIView.as_view(), name='notification-list'),
    path('unread-count/', NotificationUnreadCountAPIView.as_view(), name='notification-unread-count'),
    path('<int:pk>/read/', NotificationMarkReadAPIView.as_view(), name='notification-mark-read'),
    path('mark-all-read/', NotificationMarkAllReadAPIView.as_view(), name='notification-mark-all-read'),
    path('preferences/', NotificationPreferenceAPIView.as_view(), name='notification-preferences'),
]
