from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import SAFE_METHODS

from accounts.permissions import IsAssistantEditor, IsEditor, IsEmailVerified
from research.service import ResearchPaperService
from assistantReview.serializers import (
    AssistantReviewSerializer,
    AssistantReviewCreateSerializer,
)
from assistantReview.services import AssistantReviewService

class AssistantReviewAPIView(APIView):

    permission_classes = [IsAssistantEditor, IsEmailVerified]

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [(IsEditor | IsAssistantEditor)(), IsEmailVerified()]
        return [permission() for permission in self.permission_classes]

    def get(self, request, paper_id):

        paper = ResearchPaperService.get_paper(paper_id)

        reviews = paper.assistant_reviews.all()

        serializer = AssistantReviewSerializer(
            reviews,
            many=True
        )

        return Response(serializer.data)

    def post(self, request, paper_id):

        paper = ResearchPaperService.get_paper(paper_id)

        serializer = AssistantReviewCreateSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        review = AssistantReviewService.create_review(
            paper,
            request.user,
            serializer.validated_data
        )

        return Response(
            AssistantReviewSerializer(review).data,
            status=status.HTTP_201_CREATED
        )
