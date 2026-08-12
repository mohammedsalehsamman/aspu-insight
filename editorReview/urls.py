from django.urls import path

from editorReview.views import (
    EditorInitialReviewAPIView,
    EditorFinalReviewAPIView,
    PublishPaperAPIView,
    AssignAssistantEditorAPIView,
)

urlpatterns = [

    path(
        "papers/<int:paper_id>/assign-assistant-editor/",
        AssignAssistantEditorAPIView.as_view(),
        name="assign-assistant-editor"
    ),

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
