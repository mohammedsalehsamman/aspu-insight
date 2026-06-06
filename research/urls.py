from django.urls import path

from research.views import (
    ResearchPaperAPIView,
    ResearchPaperDetailAPIView
)

urlpatterns = [

    path(
        "papers/",
        ResearchPaperAPIView.as_view(),
        name="paper-list"
    ),

    path(
        "papers/<int:pk>/",
        ResearchPaperDetailAPIView.as_view(),
        name="paper-detail"
    ),
]