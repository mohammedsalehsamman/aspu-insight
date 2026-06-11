from django.urls import path

from editorReview.views import (
    EditorInitialReviewAPIView,
    EditorFinalReviewAPIView,
    PublishPaperAPIView,
)

urlpatterns = [

    path(
        "papers/<int:paper_id>/editor-review/initial/",
        EditorInitialReviewAPIView.as_view(),
        name="editor-review-initial"
    ),

    path(
        "papers/<int:paper_id>/editor-review/final/",
        EditorFinalReviewAPIView.as_view(),
        name="editor-review-final"
    ),

    path(
        "papers/<int:paper_id>/publish/",
        PublishPaperAPIView.as_view(),
        name="publish-paper"
    ),
]
