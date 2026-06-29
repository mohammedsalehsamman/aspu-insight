from __future__ import annotations
import logging
import time
from celery import shared_task
from pypdf import PdfReader
from research.models import ResearchPaper, PlagiarismReport, PlagiarismSource
from .services.analyzer import PlagiarismAnalyzer
from .claim_evidence.services.graph_builder import extract_graph
from .ieee_checker.services.citation_extractor import detect_language, extract_paper_title
from .ieee_checker.infrastructure.file_parser import extract_text_from_file
from .models import ClaimEvidenceGraphReport

logger = logging.getLogger(name)

def extract_text_from_pdf(pdf_path: str) -> str:
    raw_text = ""
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                raw_text += page_text + " "
    except Exception as e:
        logger.error("Error extracting text from PDF %s: %s", pdf_path, e)
    return raw_text
<<<<<<< HEAD
def extract_text_from_pdf(pdf_path: str) -> str:
    raw_text = ""
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                raw_text += page_text + " "
    except Exception as e:
        logger.error("Error extracting text from PDF %s: %s", pdf_path, e)
    return raw_text
=======
from .claim_evidence.services.graph_builder import extract_graph
from .ieee_checker.services.citation_extractor import detect_language, extract_paper_title
from .ieee_checker.infrastructure.file_parser import extract_text_from_file
from .models import ClaimEvidenceGraphReport

logger = logging.getLogger(__name__)

>>>>>>> 3106ed94207095824034bd4adf775b32acb37969

@shared_task(bind=True)
def analyze_claim_evidence_graph_task(self, report_id: int) -> dict:
    try:
        report = ClaimEvidenceGraphReport.objects.get(pk=report_id)
    except ClaimEvidenceGraphReport.DoesNotExist:
        logger.error("ClaimEvidenceGraphReport %s not found", report_id)
        return {"status": "failed", "report_id": report_id, "error": "report not found"}

    report.status = ClaimEvidenceGraphReport.Status.PROCESSING
    report.save(update_fields=["status"])

    start_time = time.time()

    try:
        file_path = report.document_file.path
        full_text, _page_count, _file_type = extract_text_from_file(file_path)

        if not full_text.strip():
            report.status = ClaimEvidenceGraphReport.Status.FAILED
            report.error_message = "تعذّر استخراج النص من الملف."
            report.processing_time_seconds = round(time.time() - start_time, 2)
            report.save(update_fields=["status", "error_message", "processing_time_seconds"])
            return {"status": "failed", "report_id": report_id, "error": "empty text"}

        if not report.paper_title:
            report.paper_title = extract_paper_title(full_text)
        if not report.detected_language:
            report.detected_language = detect_language(full_text)
        report.source_excerpt = full_text[:1000]

        graph_result = extract_graph(
            full_text,
            threshold=report.similarity_threshold,
            top_claims_count=report.top_claims_count,
        )

        if "error" in graph_result:
            report.status = ClaimEvidenceGraphReport.Status.FAILED
            report.error_message = graph_result["error"]
        else:
            report.status = ClaimEvidenceGraphReport.Status.COMPLETED
            report.graph_data = {
                "nodes": graph_result["nodes"],
                "edges": graph_result["edges"],
                "focus_graph": graph_result["focus_graph"],
                "top_claims": graph_result["top_claims"],
            }
            stats = graph_result.get("stats", {})
            report.claims_count = stats.get("claims", 0)
            report.evidence_count = stats.get("evidence", 0)
            report.neutral_count = stats.get("neutral", 0)
            report.edges_count = stats.get("edges", 0)
            report.summary = (
                f"تم تحليل {len(graph_result['nodes'])} جملة: "
                f"{report.claims_count} ادعاء، {report.evidence_count} دليل، "
                f"{report.edges_count} رابط دعم."
            )

        report.processing_time_seconds = round(time.time() - start_time, 2)
        report.save()

        return {"status": report.status, "report_id": report_id}

    except Exception as e:
        logger.exception("Claim-Evidence analysis failed for report %s: %s", report_id, e)
        report.status = ClaimEvidenceGraphReport.Status.FAILED
        report.error_message = str(e)
        report.processing_time_seconds = round(time.time() - start_time, 2)
        report.save(update_fields=["status", "error_message", "processing_time_seconds"])
        return {"status": "failed", "report_id": report_id, "error": str(e)}
@shared_task(bind=True)
def check_paper_plagiarism_task(self, paper_id: int) -> dict:
    try:
        paper = ResearchPaper.objects.get(id=paper_id)
        paper.status = 'checking_plagiarism'
        paper.save(update_fields=["status"])

        raw_text = ""
        if paper.pdf_file:
            raw_text = extract_text_from_pdf(paper.pdf_file.path)

        if not raw_text.strip():
            raw_text = paper.abstract

        # استدعاء المحلل الذكي ومعالجة القطع المتتالية
        analyzer = PlagiarismAnalyzer(api_key="YOUR_ACTUAL_API_KEY", chunk_size=30)
        report_data = analyzer.calculate_similarity(raw_text)

        # حفظ التقرير الرئيسي وحفظ الكلمات المفتاحية الذكية
        report = PlagiarismReport.objects.create(
            paper=paper,
            total_similarity_score=report_data['total_score'],
            ai_keywords=report_data.get('ai_tags', [])
        )

        # حفظ المصادر المقتبسة من الويب بدقة
        for src in report_data['sources']:
            PlagiarismSource.objects.create(
                report=report,
                source_url=src['url'],
                source_title=src['title'],
                match_percentage=src['match_percentage'],
                matched_text_snippet=src['snippet']
            )

        paper.status = 'under_review'
        paper.save(update_fields=["status"])
        return {"status": paper.status, "paper_id": paper_id}

    except Exception as e:
        logger.exception("Plagiarism check failed for paper %s: %s", paper_id, e)
        if paper:
            paper.status = 'plagiarism_failed'
            paper.save(update_fields=["status"])
        return {"status": "failed", "paper_id": paper_id, "error": str(e)}