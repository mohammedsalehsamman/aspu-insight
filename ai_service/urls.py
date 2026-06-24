from django.urls import path
from .views import (
    IEEECheckView,
    IEEEReportListView,
    IEEEReportDetailView,
    ClaimEvidenceGraphAnalyzeView,
    ClaimEvidenceGraphReportListView,
    ClaimEvidenceGraphReportDetailView,
)

app_name = 'ai_service'

urlpatterns = [
    path('ieee/check/', IEEECheckView.as_view(), name='ieee-check'),
    path('ieee/reports/', IEEEReportListView.as_view(), name='ieee-report-list'),
    path('ieee/reports/<int:pk>/', IEEEReportDetailView.as_view(), name='ieee-report-detail'),

    path('claim-evidence/analyze/', ClaimEvidenceGraphAnalyzeView.as_view(), name='claim-evidence-analyze'),
    path('claim-evidence/reports/', ClaimEvidenceGraphReportListView.as_view(), name='claim-evidence-report-list'),
    path('claim-evidence/reports/<int:pk>/', ClaimEvidenceGraphReportDetailView.as_view(), name='claim-evidence-report-detail'),
]
