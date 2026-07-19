from django.urls import path

from dashboard.views import (
    AdminDashboardStatsView,
    AdminPaperListView,
    AdminPaperDetailView,
    AdminAssignEditorView,
    AdminEditorReviewListView,
    AdminAssistantReviewListView,
    AdminCommitteeListView,
)

urlpatterns = [
    path('stats/', AdminDashboardStatsView.as_view(), name='admin-dashboard-stats'),
    path('papers/', AdminPaperListView.as_view(), name='admin-dashboard-papers'),
    path('papers/<int:pk>/', AdminPaperDetailView.as_view(), name='admin-dashboard-paper-detail'),
    path('papers/<int:pk>/assign-editor/', AdminAssignEditorView.as_view(), name='admin-dashboard-assign-editor'),
    path('editor-reviews/', AdminEditorReviewListView.as_view(), name='admin-dashboard-editor-reviews'),
    path('assistant-reviews/', AdminAssistantReviewListView.as_view(), name='admin-dashboard-assistant-reviews'),
    path('committees/', AdminCommitteeListView.as_view(), name='admin-dashboard-committees'),
]
