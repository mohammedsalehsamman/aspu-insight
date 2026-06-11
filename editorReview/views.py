from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from accounts.permissions import IsEditor
from research.service import ResearchPaperService
from editorReview.models import EditorReview
from editorReview.serializers import (
    EditorReviewSerializer,
    EditorInitialReviewSerializer,
    EditorFinalReviewSerializer,
)
from editorReview.services import EditorReviewService


class EditorInitialReviewAPIView(APIView):

    permission_classes = [IsEditor]

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

    permission_classes = [IsEditor]

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

    permission_classes = [IsEditor]

    def post(self, request, paper_id):

        paper = ResearchPaperService.get_paper(paper_id)

        paper = EditorReviewService.publish_paper(
            paper,
            request.user
        )

        return Response(
            {
                "research_id": paper.research_id,
                "status": paper.status,
            }
        )
