from django.urls import path
from .views import (
    ResearchPaperListCreateAPIView,
    ResearchPaperDetailAPIView,
    ResearchPaperDownloadAPIView,
    ResearchPaperPlagiarismReportView,
    SubmitAssistantEditorReportAPIView,
    AuthorDashboardAPIView
)

urlpatterns = [
    path('papers/', ResearchPaperListCreateAPIView.as_view(), name='paper-list-create'),
    path('papers/<int:paper_id>/', ResearchPaperDetailAPIView.as_view(), name='paper-detail'),
    path('papers/<int:paper_id>/download/', ResearchPaperDownloadAPIView.as_view(), name='paper-download'),
    path('papers/<int:paper_id>/plagiarism-report/', ResearchPaperPlagiarismReportView.as_view(), name='paper-plagiarism-report'),
    path('papers/<int:paper_id>/submit-assistant-report/', SubmitAssistantEditorReportAPIView.as_view(), name='submit-assistant-report'),
    path('author/dashboard/', AuthorDashboardAPIView.as_view(), name='author-dashboard'),
]