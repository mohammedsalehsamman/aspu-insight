from django.urls import path
from .views import (
    ResearchPaperListCreateAPIView, 
    ResearchPaperDetailAPIView,
    ResearchPaperDownloadAPIView
)

urlpatterns = [
    path('papers/', ResearchPaperListCreateAPIView.as_view(), name='paper-list-create'),
    path('papers/<int:paper_id>/', ResearchPaperDetailAPIView.as_view(), name='paper-detail'),
    path('papers/<int:paper_id>/download/', ResearchPaperDownloadAPIView.as_view(), name='paper-download'),
]