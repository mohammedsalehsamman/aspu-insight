from django.urls import path
from .views import (
    IEEECheckView,
    IEEEReportListView,
    IEEEReportDetailView,
)

app_name = 'ai_service'

urlpatterns = [
    path('ieee/check/', IEEECheckView.as_view(), name='ieee-check'),
    path('ieee/reports/', IEEEReportListView.as_view(), name='ieee-report-list'),
    path('ieee/reports/<int:pk>/', IEEEReportDetailView.as_view(), name='ieee-report-detail'),
]
