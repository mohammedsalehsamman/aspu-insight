from django.http import FileResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticatedOrReadOnly, AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from .models import ResearchPaper, PlagiarismReport
from .serializers import ResearchPaperDetailSerializer, PlagiarismReportSerializer
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
            paper = ResearchPaperService.create_paper(
                user=request.user, 
                validated_data=serializer.validated_data
            )
            output_serializer = ResearchPaperDetailSerializer(paper, context={'request': request})
            return Response(output_serializer.data, status=status.HTTP_201_CREATED)
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

class ResearchPaperPlagiarismReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, paper_id):
        try:
            paper = ResearchPaper.objects.get(id=paper_id)
        except ResearchPaper.DoesNotExist:
            return Response({"error": "البحث غير موجود"}, status=status.HTTP_404_NOT_FOUND)

        if paper.author != request.user and not request.user.is_staff and not getattr(request.user, 'is_assistant_editor', False):
            return Response({"error": "غير مصرح لك باستعراض هذا التقرير"}, status=status.HTTP_403_FORBIDDEN)

        try:
            report = paper.plagiarism_report
        except PlagiarismReport.DoesNotExist:
            return Response({"message": "التقرير غير جاهز بعد أو البحث ما زال في طور الفحص"}, status=status.HTTP_204_NO_CONTENT)

        serializer = PlagiarismReportSerializer(report)
        return Response(serializer.data, status=status.HTTP_200_OK)

class SubmitAssistantEditorReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, paper_id):
        if not getattr(request.user, 'is_assistant_editor', False):
            return Response({"detail": "Only assistant editors can perform this action."}, status=status.HTTP_403_FORBIDDEN)
            
        try:
            paper = ResearchPaper.objects.get(id=paper_id)
        except ResearchPaper.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
            
        report_text = request.data.get('report')
        if not report_text:
            return Response({"detail": "Report text is required."}, status=status.HTTP_400_BAD_REQUEST)
            
        ResearchPaperService.submit_assistant_report(paper, report_text)
        return Response({"detail": "Report submitted successfully."}, status=status.HTTP_200_OK)

class AuthorDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        papers = ResearchPaperService.get_author_dashboard_papers(request.user)
        serializer = ResearchPaperDetailSerializer(papers, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)