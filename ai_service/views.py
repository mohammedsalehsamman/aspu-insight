import logging

from django.conf import settings
from django.core.files.storage import default_storage
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsEditor, IsAssistantEditor, IsEmailVerified
from .models import IEEECheckReport, ClaimEvidenceGraphReport
from .serializers import (
    IEEECheckReportSerializer,
    IEEECheckReportListSerializer,
    ClaimEvidenceGraphReportSerializer,
    ClaimEvidenceGraphReportListSerializer,
)
from .tasks import analyze_claim_evidence_graph_task, analyze_ieee_check_task
from .validators import validate_pdf_or_docx_content

logger = logging.getLogger(__name__)

class KeywordSuggestionView(APIView):

    permission_classes = [IsAuthenticated, IsEmailVerified]

    def post(self, request, *args, **kwargs):
        text = (request.data.get('text') or '').strip()
        paper_id = request.data.get('paper_id')

        if not text and paper_id:
            from research.models import ResearchPaper
            try:
                paper = ResearchPaper.objects.get(id=paper_id)
            except ResearchPaper.DoesNotExist:
                return Response({"error": "البحث غير موجود."}, status=status.HTTP_404_NOT_FOUND)
            text = f"{paper.title} {paper.abstract}".strip()

        if not text:
            return Response(
                {"error": "يجب إرسال الحقل 'text' أو 'paper_id'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from ai_service.utils.ai_keywordExtractor import AIKeywordExtractor
            keywords = AIKeywordExtractor().extract_pure_keywords(text, top_n=10)
        except Exception as e:
            logger.exception("Keyword suggestion unavailable (non-blocking): %s", e)
            return Response(
                {"keywords": [], "note": "خدمة اقتراح الكلمات المفتاحية غير متاحة حالياً."},
                status=status.HTTP_200_OK,
            )

        return Response({"keywords": keywords}, status=status.HTTP_200_OK)

class IEEECheckView(APIView):

    parser_classes  = [MultiPartParser, FormParser]
    permission_classes = [IsEditor | IsAssistantEditor, IsEmailVerified]

    def post(self, request, *args, **kwargs):
        document_file = request.FILES.get('document_file')
        if not document_file:
            document_file = request.FILES.get('pdf_file')
            if not document_file:
                return Response(
                    {"error": "الحقل 'document_file' مطلوب. أرسل ملف PDF أو DOCX."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        content_error = validate_pdf_or_docx_content(document_file)
        if content_error:
            return Response({"error": content_error}, status=status.HTTP_400_BAD_REQUEST)

        max_size = 10 * 1024 * 1024
        if document_file.size > max_size:
            return Response(
                {"error": "حجم الملف يتجاوز الحد المسموح (10 MB)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        verify_crossref = request.data.get('verify_crossref', 'true').lower() == 'true'

        report = IEEECheckReport(
            original_filename=document_file.name,
            status=IEEECheckReport.Status.PENDING,
            full_result={"verify_crossref": verify_crossref},
        )
        if request.user and request.user.is_authenticated:
            report.requested_by = request.user

        report.pdf_file.save(document_file.name, document_file, save=False)
        report.save()

        try:
            analyze_ieee_check_task.delay(report.id)
        except Exception as e:
            logger.exception("IEEE check task dispatch failed: %s", e)
            report.refresh_from_db()
            if report.status == IEEECheckReport.Status.PENDING:
                report.status = IEEECheckReport.Status.ERROR
                report.summary = f"فشل تشغيل التحليل: {str(e)}"
                report.save(update_fields=["status", "summary"])

        report.refresh_from_db()
        serializer = IEEECheckReportSerializer(report)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class IEEEReportListView(APIView):
    permission_classes = [IsEditor | IsAssistantEditor, IsEmailVerified]

    def get(self, request, *args, **kwargs):
        reports = IEEECheckReport.objects.all()

        status_filter = request.query_params.get('status')
        if status_filter:
            reports = reports.filter(status=status_filter)

        if request.user and request.user.is_authenticated:
            mine = request.query_params.get('mine', 'false').lower()
            if mine == 'true':
                reports = reports.filter(requested_by=request.user)

        serializer = IEEECheckReportListSerializer(reports[:50], many=True)
        return Response(serializer.data)

class IEEEReportDetailView(APIView):
    permission_classes = [IsEditor | IsAssistantEditor, IsEmailVerified]

    def _get_report(self, pk):
        try:
            return IEEECheckReport.objects.get(pk=pk)
        except IEEECheckReport.DoesNotExist:
            return None

    def get(self, request, pk, *args, **kwargs):
        report = self._get_report(pk)
        if not report:
            return Response({"error": "التقرير غير موجود"}, status=status.HTTP_404_NOT_FOUND)
        serializer = IEEECheckReportSerializer(report)
        return Response(serializer.data)

    def delete(self, request, pk, *args, **kwargs):
        report = self._get_report(pk)
        if not report:
            return Response({"error": "التقرير غير موجود"}, status=status.HTTP_404_NOT_FOUND)
        try:
            if report.pdf_file:
                default_storage.delete(report.pdf_file.name)
        except Exception:
            pass
        report.delete()
        return Response({"message": "تم حذف التقرير بنجاح"}, status=status.HTTP_204_NO_CONTENT)

class ClaimEvidenceGraphAnalyzeView(APIView):

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsEditor | IsAssistantEditor, IsEmailVerified]

    def post(self, request, *args, **kwargs):
        document_file = request.FILES.get('document_file')
        if not document_file:
            return Response(
                {"error": "الحقل 'document_file' مطلوب. أرسل ملف PDF أو DOCX."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_error = validate_pdf_or_docx_content(document_file)
        if content_error:
            return Response({"error": content_error}, status=status.HTTP_400_BAD_REQUEST)

        max_size = 10 * 1024 * 1024
        if document_file.size > max_size:
            return Response(
                {"error": "حجم الملف يتجاوز الحد المسموح (10 MB)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        threshold_raw = request.data.get('similarity_threshold')
        try:
            threshold = (
                float(threshold_raw) if threshold_raw is not None
                else getattr(settings, 'CLAIM_EVIDENCE_SIMILARITY_THRESHOLD', 0.5)
            )
        except (TypeError, ValueError):
            threshold = getattr(settings, 'CLAIM_EVIDENCE_SIMILARITY_THRESHOLD', 0.5)
        threshold = max(0.0, min(1.0, threshold))

        top_claims_raw = request.data.get('top_claims_count')
        try:
            top_claims_count = (
                int(top_claims_raw) if top_claims_raw is not None
                else getattr(settings, 'CLAIM_EVIDENCE_TOP_CLAIMS_COUNT', 10)
            )
        except (TypeError, ValueError):
            top_claims_count = getattr(settings, 'CLAIM_EVIDENCE_TOP_CLAIMS_COUNT', 10)
        top_claims_count = max(1, min(50, top_claims_count))

        report = ClaimEvidenceGraphReport(
            original_filename=document_file.name,
            similarity_threshold=threshold,
            top_claims_count=top_claims_count,
        )
        if request.user and request.user.is_authenticated:
            report.requested_by = request.user

        report.document_file.save(document_file.name, document_file, save=False)
        report.save()

        try:
            analyze_claim_evidence_graph_task.delay(report.id)
        except Exception as e:
            logger.exception("Claim-Evidence task dispatch failed: %s", e)
            report.refresh_from_db()
            if report.status == ClaimEvidenceGraphReport.Status.PENDING:
                report.status = ClaimEvidenceGraphReport.Status.FAILED
                report.error_message = f"فشل تشغيل التحليل: {str(e)}"
                report.save(update_fields=["status", "error_message"])

        report.refresh_from_db()
        serializer = ClaimEvidenceGraphReportSerializer(report)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class ClaimEvidenceGraphReportListView(APIView):
    permission_classes = [IsEditor | IsAssistantEditor, IsEmailVerified]

    def get(self, request, *args, **kwargs):
        reports = ClaimEvidenceGraphReport.objects.all()

        status_filter = request.query_params.get('status')
        if status_filter:
            reports = reports.filter(status=status_filter)

        if request.user and request.user.is_authenticated:
            mine = request.query_params.get('mine', 'false').lower()
            if mine == 'true':
                reports = reports.filter(requested_by=request.user)

        serializer = ClaimEvidenceGraphReportListSerializer(reports[:50], many=True)
        return Response(serializer.data)

class ClaimEvidenceGraphReportDetailView(APIView):
    permission_classes = [IsEditor | IsAssistantEditor, IsEmailVerified]

    def _get_report(self, pk):
        try:
            return ClaimEvidenceGraphReport.objects.get(pk=pk)
        except ClaimEvidenceGraphReport.DoesNotExist:
            return None

    def _forbidden_if_not_owner(self, request, report):
        if report.requested_by_id is None:
            if request.user.role != 'admin':
                return Response({"error": "غير مصرح لك بالوصول إلى هذا التقرير"}, status=status.HTTP_403_FORBIDDEN)
        elif report.requested_by_id != request.user.pk and request.user.role != 'admin':
            return Response({"error": "غير مصرح لك بالوصول إلى هذا التقرير"}, status=status.HTTP_403_FORBIDDEN)
        return None

    def get(self, request, pk, *args, **kwargs):
        report = self._get_report(pk)
        if not report:
            return Response({"error": "التقرير غير موجود"}, status=status.HTTP_404_NOT_FOUND)
        forbidden = self._forbidden_if_not_owner(request, report)
        if forbidden:
            return forbidden
        serializer = ClaimEvidenceGraphReportSerializer(report)
        return Response(serializer.data)

    def delete(self, request, pk, *args, **kwargs):
        report = self._get_report(pk)
        if not report:
            return Response({"error": "التقرير غير موجود"}, status=status.HTTP_404_NOT_FOUND)
        forbidden = self._forbidden_if_not_owner(request, report)
        if forbidden:
            return forbidden
        try:
            if report.document_file:
                default_storage.delete(report.document_file.name)
        except Exception:
            pass
        report.delete()
        return Response({"message": "تم حذف التقرير بنجاح"}, status=status.HTTP_204_NO_CONTENT)
