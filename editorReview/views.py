from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from accounts.permissions import IsEditor, IsEmailVerified
from accounts.serializers import UserListSerializer
from research.service import ResearchPaperService
from editorReview.models import EditorReview
from editorReview.serializers import (
    EditorReviewSerializer,
    EditorInitialReviewSerializer,
    EditorFinalReviewSerializer,
    AssignAssistantEditorSerializer,
)
from editorReview.services import EditorReviewService

class EditorInitialReviewAPIView(APIView):

    permission_classes = [IsEditor, IsEmailVerified]

    def get(self, request, paper_id):

        paper = ResearchPaperService.get_paper(paper_id)

        reviews = paper.editor_reviews.filter(
            stage=EditorReview.Stage.INITIAL
        )

        serializer = EditorReviewSerializer(
            reviews,
            many=True
        )

        return Response(serializer.data)

    def post(self, request, paper_id):

        paper = ResearchPaperService.get_paper(paper_id)

        serializer = EditorInitialReviewSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        review = EditorReviewService.create_initial_review(
            paper,
            request.user,
            serializer.validated_data
        )

        return Response(
            EditorReviewSerializer(review).data,
            status=status.HTTP_201_CREATED
        )

class EditorFinalReviewAPIView(APIView):

    permission_classes = [IsEditor, IsEmailVerified]

    def get(self, request, paper_id):

        paper = ResearchPaperService.get_paper(paper_id)

        reviews = paper.editor_reviews.filter(
            stage=EditorReview.Stage.FINAL
        )

        serializer = EditorReviewSerializer(
            reviews,
            many=True
        )

        return Response(serializer.data)

    def post(self, request, paper_id):

        paper = ResearchPaperService.get_paper(paper_id)

        serializer = EditorFinalReviewSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        review = EditorReviewService.create_final_review(
            paper,
            request.user,
            serializer.validated_data
        )

        return Response(
            EditorReviewSerializer(review).data,
            status=status.HTTP_201_CREATED
        )

class PublishPaperAPIView(APIView):

    permission_classes = [IsEditor, IsEmailVerified]

    def post(self, request, paper_id):

        paper = ResearchPaperService.get_paper(paper_id)

        paper = EditorReviewService.publish_paper(
            paper,
            request.user
        )

        return Response(
            {
                "id": paper.id,
                "status": paper.status,
            }
        )

class AssignAssistantEditorAPIView(APIView):

    permission_classes = [IsEditor, IsEmailVerified]

    def patch(self, request, paper_id):

        paper = ResearchPaperService.get_paper(paper_id)

        serializer = AssignAssistantEditorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        paper = EditorReviewService.assign_assistant_editor(
            paper,
            request.user,
            serializer.validated_data["assistant_editor_id"]
        )

        return Response(
            {
                "id": paper.id,
                "assigned_assistant_editor": (
                    UserListSerializer(paper.assigned_assistant_editor).data
                    if paper.assigned_assistant_editor else None
                ),
            }
        )
