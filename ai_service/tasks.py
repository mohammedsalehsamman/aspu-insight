"""
Celery tasks for ai_service.

Currently runs in `CELERY_TASK_ALWAYS_EAGER` mode (synchronous, in-process)
- see `aspu_insight/celery.py` and `aspu_insight/settings.py`. The task is
written as a normal `@shared_task` so that switching to a real broker
later (Redis + a running worker) requires no code changes here.
"""
from __future__ import annotations

import logging
import time

from celery import shared_task

from .claim_evidence.services.graph_builder import extract_graph
from .ieee_checker.services.citation_extractor import detect_language, extract_paper_title
from .ieee_checker.infrastructure.file_parser import extract_text_from_file
from .models import ClaimEvidenceGraphReport

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def analyze_claim_evidence_graph_task(self, report_id: int) -> dict:
    """Run the Claim-to-Evidence Graph analysis for a `ClaimEvidenceGraphReport`.

    Loads the report's uploaded document, extracts its text, runs
    `extract_graph()`, and updates the report's status/graph_data/summary
    fields in place. Any failure (unreadable file, malformed/unintelligible
    text, model error, ...) is caught and recorded on the report as
    `status=FAILED` + `error_message`, so a single bad document cannot crash
    the worker.

    In `CELERY_TASK_ALWAYS_EAGER` mode this executes synchronously when
    `.delay()` is called from the view.

    Args:
        report_id: Primary key of the `ClaimEvidenceGraphReport` to process.

    Returns:
        A small dict summary `{"status": str, "report_id": int, ...}`.
    """
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
