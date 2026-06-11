from django.urls import path

from assistantReview.views import AssistantReviewAPIView

urlpatterns = [

    path(
        "papers/<int:paper_id>/assistant-review/",
        AssistantReviewAPIView.as_view(),
        name="assistant-review"
    ),
]
