from django.http import FileResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticatedOrReadOnly, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from .models import ResearchPaper
from .serializers import ResearchPaperDetailSerializer 
from configuration.models import JournalConfiguration
from .service import ResearchPaperService

class ResearchPaperListCreateAPIView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        papers = ResearchPaperService.get_visible_papers(request.user)
        serializer = ResearchPaperDetailSerializer(papers, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ResearchPaperDetailSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save(author=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class ResearchPaperDetailAPIView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_object(self, paper_id):
        try:
            return ResearchPaper.objects.select_related('author').get(id=paper_id)
        except ResearchPaper.DoesNotExist:
            return None

    def get(self, request, paper_id):
        paper = self.get_object(paper_id)
        if not paper:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
        if not ResearchPaperService.can_view(request.user, paper):
            return Response({"detail": "Not authorized to view this paper."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ResearchPaperDetailSerializer(paper, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, paper_id):
        paper = self.get_object(paper_id)
        if not paper:
            return Response(status=status.HTTP_404_NOT_FOUND)
            
        if paper.author != request.user and not request.user.is_staff:
            return Response(status=status.HTTP_403_FORBIDDEN)
            
        serializer = ResearchPaperDetailSerializer(paper, data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, paper_id):
        paper = self.get_object(paper_id)
        if not paper:
            return Response(status=status.HTTP_404_NOT_FOUND)
            
        if paper.author != request.user and not request.user.is_staff:
            return Response(status=status.HTTP_403_FORBIDDEN)
            
        paper.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class ResearchPaperDownloadAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, paper_id):
        try:
            paper = ResearchPaper.objects.get(id=paper_id)
        except ResearchPaper.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not paper.pdf_file:
            return Response(status=status.HTTP_404_NOT_FOUND)

        user = request.user

        if user.is_authenticated and (user.is_staff or user.is_superuser or user == paper.author):
            return FileResponse(paper.pdf_file.open('rb'), as_attachment=True, content_type='application/pdf')

        config = JournalConfiguration.objects.first()
        current_mode = config.system_mode if config else 'full_open'

        if current_mode == 'full_open':
            return FileResponse(paper.pdf_file.open('rb'), as_attachment=True, content_type='application/pdf')
        if current_mode == 'hybrid' and paper.is_paid_open_access:
            return FileResponse(paper.pdf_file.open('rb'), as_attachment=True, content_type='application/pdf')

        return Response(status=status.HTTP_403_FORBIDDEN)
        