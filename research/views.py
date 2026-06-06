from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from research.serializers import ResearchPaperSerializer
from research.service import ResearchPaperService


class ResearchPaperAPIView(APIView):

    def get(self, request):

        papers = ResearchPaperService.get_visible_papers(
            request.user
        )

        serializer = ResearchPaperSerializer(
            papers,
            many=True
        )

        return Response(serializer.data)

    def post(self, request):

        serializer = ResearchPaperSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        paper = ResearchPaperService.create_paper(
            request.user,
            serializer.validated_data
        )

        return Response(
            ResearchPaperSerializer(paper).data,
            status=status.HTTP_201_CREATED
        )


class ResearchPaperDetailAPIView(APIView):

    def get(self, request, pk):

        paper = ResearchPaperService.get_paper(pk)

        if not ResearchPaperService.can_view(
            request.user,
            paper
        ):
            return Response(
                {"detail": "Permission denied"},
                status=403
            )

        serializer = ResearchPaperSerializer(
            paper
        )

        return Response(serializer.data)

    def put(self, request, pk):

        paper = ResearchPaperService.get_paper(pk)

        if not ResearchPaperService.can_update(
            request.user,
            paper
        ):
            return Response(
                {"detail": "Update not allowed"},
                status=403
            )

        serializer = ResearchPaperSerializer(
            paper,
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        paper = ResearchPaperService.update_paper(
            paper,
            serializer.validated_data
        )

        return Response(
            ResearchPaperSerializer(paper).data
        )

    def delete(self, request, pk):

        paper = ResearchPaperService.get_paper(pk)

        if not ResearchPaperService.can_delete(
            request.user,
            paper
        ):
            return Response(
                {"detail": "Delete not allowed"},
                status=403
            )

        ResearchPaperService.delete_paper(
            paper
        )

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )