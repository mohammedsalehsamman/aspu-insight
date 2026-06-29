from django.http import FileResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticatedOrReadOnly, AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
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

class SubmitAssistantEditorReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, paper_id):
        if not getattr(request.user, 'is_assistant_editor', False):
            return Response({"detail": "Only assistant editors can perform this action."}, status=status.HTTP_403_FORBIDDEN)
        
        paper = get_object_or_404(ResearchPaper, id=paper_id)
        report_text = request.data.get('assistant_report')
        
        if not report_text:
            return Response({"detail": "assistant_report field is required."}, status=status.HTTP_400_BAD_REQUEST)
            
        paper.assistant_report = report_text
        paper.is_reviewed_by_assistant = True
        paper.save()
        return Response({"detail": "Report submitted successfully."}, status=status.HTTP_200_OK)

class ResearchPaperPlagiarismReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, paper_id):
        paper = get_object_or_404(ResearchPaper, id=paper_id)
        
        if paper.author == request.user:
            if not paper.is_reviewed_by_assistant and not request.user.is_staff:
                return Response({"error": "غير مصرح لك باستعراض هذا التقرير في هذه المرحلة"}, status=status.HTTP_403_FORBIDDEN)
        elif not request.user.is_staff and not getattr(request.user, 'is_assistant_editor', False):
            from committees.models import Committee, CommitteeMember
            is_editor = Committee.objects.filter(paper=paper, editor=request.user).exists()
            is_reviewer = CommitteeMember.objects.filter(committee__paper=paper, user=request.user).exists()
            
            if (is_editor or is_reviewer) and not paper.is_reviewed_by_assistant:
                return Response({"error": "غير مصرح لك باستعراض التقرير قبل انتهاء مراجعة مساعد المحرر"}, status=status.HTTP_403_FORBIDDEN)
            if not is_editor and not is_reviewer:
                return Response({"error": "غير مصرح لك باستعراض هذا التقرير"}, status=status.HTTP_403_FORBIDDEN)

        try:
            report = paper.plagiarism_report
            sources = report.sources.all()
            
            total_score = report.total_similarity_score
            sources_count = sources.count()
            
            if total_score < 15.0:
                risk_level = "Low (Safe)"
                action_required = "Auto-approve or proceed to standard peer-review"
            elif 15.0 <= total_score <= 30.0:
                risk_level = "Medium (Warning)"
                action_required = "Review highlighted sentences in the report"
            else:
                risk_level = "High (Danger)"
                action_required = "Immediate rejection recommended"

            highest_match = max([src.match_percentage for src in sources]) if sources else 0.0
            
            if highest_match > 50.0:
                pattern = "Concentrated Plagiarism (Heavy copying from a single web source)"
            elif sources_count > 5 and total_score > 20.0:
                pattern = "Mosaic Plagiarism (Patchwork / structural copying from multiple sources)"
            elif total_score > 0.0:
                pattern = "Standard citations / Distributed similarity"
            else:
                pattern = "No similarity detected (Completely Original)"

            plagiarism_penalty = total_score * 1.2
            source_penalty = min(sources_count * 1.5, 15.0)
            
            integrity_score = 100.0 - (plagiarism_penalty + source_penalty)
            integrity_score = max(0.0, round(integrity_score, 2))

            sources_data = [
                {
                    "source_title": src.source_title,
                    "source_url": src.source_url,
                    "match_percentage": round(src.match_percentage, 2),
                    "matched_text_snippet": src.matched_text_snippet
                } for src in sources
            ]

            return Response({
                "paper_id": paper.id,
                "paper_title": paper.title if hasattr(paper, 'title') else f"Paper #{paper.id}",
                "automated_evaluation": {
                    "research_integrity_score": f"{integrity_score}/100",
                    "risk_level": risk_level,
                    "recommended_action": action_required,
                    "detected_plagiarism_pattern": pattern
                },
                "raw_metrics": {
                    "total_similarity_score": round(total_score, 2),
                    "distinct_sources_found": sources_count,
                    "ai_keywords": report.ai_keywords if hasattr(report, 'ai_keywords') else []
                },
                "detailed_sources": sources_data
            }, status=status.HTTP_200_OK)

        except PlagiarismReport.DoesNotExist:
            return Response({
                "paper_id": paper.id,
                "status": paper.status,
                "message": "تقرير الفحص غير موجود أو قيد المعالجة حالياً بواسطة نظام الذكاء الاصطناعي والـ Celery."
            }, status=status.HTTP_204_NO_CONTENT)

class AuthorDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        papers = ResearchPaperService.get_author_dashboard_papers(request.user)
        serializer = ResearchPaperDetailSerializer(papers, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)