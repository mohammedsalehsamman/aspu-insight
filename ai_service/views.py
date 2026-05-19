import os
import time
import logging
import tempfile

from django.core.files.storage import default_storage
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .ieee import perform_ieee_analysis
from .models import IEEECheckReport
from .serializers import IEEECheckReportSerializer, IEEECheckReportListSerializer

logger = logging.getLogger(__name__)


class IEEECheckView(APIView):

    parser_classes  = [MultiPartParser, FormParser]
    permission_classes = [AllowAny]   

    def post(self, request, *args, **kwargs):
        document_file = request.FILES.get('document_file')
        if not document_file:
            document_file = request.FILES.get('pdf_file')
            if not document_file:
                return Response(
                    {"error": "الحقل 'document_file' مطلوب. أرسل ملف PDF أو DOCX."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        file_name_lower = document_file.name.lower()
        if not (file_name_lower.endswith('.pdf') or file_name_lower.endswith('.docx')):
            return Response(
                {"error": "يُقبل ملف PDF (.pdf) أو DOCX (.docx) فقط"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        max_size = 10 * 1024 * 1024
        if document_file.size > max_size:
            return Response(
                {"error": "حجم الملف يتجاوز الحد المسموح (10 MB)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        verify_crossref = request.data.get('verify_crossref', 'true').lower() == 'true'

        tmp_path = None
        start_time = time.time()

        try:
            file_ext = os.path.splitext(document_file.name)[1].lower()
            with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp:
                for chunk in document_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

            raw_result = perform_ieee_analysis(
                file_path=tmp_path,
                verify_crossref=verify_crossref,
                max_crossref_calls=5,
            )

        except Exception as e:
            logger.exception("IEEE analysis failed: %s", e)
            return Response(
                {"error": f"فشل في معالجة الملف: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        processing_time = round(time.time() - start_time, 2)

        try:
            report = IEEECheckReport(
                original_filename=document_file.name,
                paper_title=raw_result.get('paper_title', ''),
                detected_language=raw_result.get('detected_language', ''),
                total_pages=raw_result.get('total_pages', 0),
                total_citations_in_text=len(raw_result.get('citations_in_text', [])),
                total_references=raw_result.get('total_references', 0),
                missing_citations_count=len(raw_result.get('citations_missing_from_references', [])),
                unused_references_count=len(raw_result.get('unused_references', [])),
                citation_matching_score=raw_result.get('citation_matching_score', 0.0),
                format_score=raw_result.get('format_score', 0.0),
                crossref_score=raw_result.get('crossref_score', 0.0),
                overall_score=raw_result.get('overall_score', 0.0),
                status=raw_result.get('status', 'error'),
                summary=raw_result.get('summary', ''),
                crossref_checked=raw_result.get('crossref_checked', 0),
                crossref_verified=raw_result.get('crossref_verified_count', 0),
                processing_time_seconds=processing_time,
                full_result=raw_result,
            )
            if request.user and request.user.is_authenticated:
                report.requested_by = request.user

            report.pdf_file.save(document_file.name, document_file, save=False)
            report.save()

        except Exception as e:
            logger.warning("Failed to save report to DB: %s", e)
            raw_result['report_id'] = None
            raw_result['processing_time_seconds'] = processing_time
            return Response(raw_result, status=status.HTTP_201_CREATED)

        response_data = {
            "report_id":               report.id,
            "status":                  report.status,
            "status_display":          report.status_display_ar,
            "overall_score":           report.overall_score,
            "citation_matching_score": report.citation_matching_score,
            "format_score":            report.format_score,
            "crossref_score":          report.crossref_score,
            "paper_title":             report.paper_title,
            "detected_language":       report.detected_language,
            "total_pages":             report.total_pages,
            "total_references":        report.total_references,
            "total_citations_in_text": report.total_citations_in_text,
            "missing_citations_count": report.missing_citations_count,
            "unused_references_count": report.unused_references_count,
            "crossref_checked":        report.crossref_checked,
            "crossref_verified":       report.crossref_verified,
            "processing_time_seconds": processing_time,
            "summary":                 report.summary,
            "recommendations":         raw_result.get('recommendations', []),
            "format_issues_summary":   raw_result.get('format_issues_summary', []),
            "citations_missing":       raw_result.get('citations_missing_from_references', []),
            "unused_references":       raw_result.get('unused_references', []),
            "references":              raw_result.get('references', []),
        }

        return Response(response_data, status=status.HTTP_201_CREATED)


class IEEEReportListView(APIView):
    permission_classes = [AllowAny]

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
    permission_classes = [AllowAny]

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
