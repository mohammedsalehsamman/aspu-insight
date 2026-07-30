from __future__ import annotations
import logging
import time
from celery import shared_task
from pypdf import PdfReader
from research.models import ResearchPaper, PlagiarismReport, PlagiarismSource, PaperEmbedding
from .models import ClaimEvidenceGraphReport, IEEECheckReport
from researchHistory.services import log_status_change

logger = logging.getLogger(__name__)

try:
    from .plagiarism.services.internal_similarity import store_chunk_embeddings, find_internal_matches
    from .plagiarism.services.external_sources import run_external_check
    from .utils.ai_keywordExtractor import AIKeywordExtractor
except Exception:
    logger.exception("Plagiarism detection services unavailable; plagiarism checks will be skipped.")
    store_chunk_embeddings = None
    find_internal_matches = None
    run_external_check = None
    AIKeywordExtractor = None

try:
    from .utils.embeddings import get_embedding_model
    from .services.research_recommendation import _paper_text
except Exception:
    logger.exception("Paper embedding precomputation unavailable; search/recommendations will fall back to live encoding.")
    get_embedding_model = None
    _paper_text = None

try:
    from .claim_evidence.services.graph_builder import extract_graph
except Exception:
    logger.exception("Claim-Evidence graph builder unavailable.")
    extract_graph = None

try:
    from .ieee_checker.services.citation_extractor import detect_language, extract_paper_title
    from .ieee_checker.services.analyzer import perform_ieee_analysis
    from .ieee_checker.infrastructure.file_parser import extract_text_from_file
except Exception:
    logger.exception("IEEE checker services unavailable.")
    detect_language = extract_paper_title = perform_ieee_analysis = extract_text_from_file = None

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
            language=report.detected_language,
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
def analyze_ieee_check_task(self, report_id: int) -> dict:
    try:
        report = IEEECheckReport.objects.get(pk=report_id)
    except IEEECheckReport.DoesNotExist:
        logger.error("IEEECheckReport %s not found", report_id)
        return {"status": "failed", "report_id": report_id, "error": "report not found"}

    start_time = time.time()

    try:
        file_path = report.pdf_file.path
        raw_result = perform_ieee_analysis(
            file_path=file_path,
            verify_crossref=report.full_result.get("verify_crossref", True),
            max_crossref_calls=5,
        )

        processing_time = round(time.time() - start_time, 2)

        report.paper_title = raw_result.get('paper_title', '')
        report.detected_language = raw_result.get('detected_language', '')
        report.total_pages = raw_result.get('total_pages', 0)
        report.total_citations_in_text = len(raw_result.get('citations_in_text', []))
        report.total_references = raw_result.get('total_references', 0)
        report.missing_citations_count = len(raw_result.get('citations_missing_from_references', []))
        report.unused_references_count = len(raw_result.get('unused_references', []))
        report.citation_matching_score = raw_result.get('citation_matching_score', 0.0)
        report.format_score = raw_result.get('format_score', 0.0)
        report.crossref_score = raw_result.get('crossref_score', 0.0)
        report.overall_score = raw_result.get('overall_score', 0.0)
        report.status = raw_result.get('status', IEEECheckReport.Status.ERROR)
        report.summary = raw_result.get('summary', '')
        report.crossref_checked = raw_result.get('crossref_checked', 0)
        report.crossref_verified = raw_result.get('crossref_verified_count', 0)
        report.processing_time_seconds = processing_time
        report.full_result = raw_result
        report.save()

        return {"status": report.status, "report_id": report_id}

    except Exception as e:
        logger.exception("IEEE analysis failed for report %s: %s", report_id, e)
        report.status = IEEECheckReport.Status.ERROR
        report.summary = f"فشل في معالجة الملف: {str(e)}"
        report.processing_time_seconds = round(time.time() - start_time, 2)
        report.save(update_fields=["status", "summary", "processing_time_seconds"])
        return {"status": "failed", "report_id": report_id, "error": str(e)}

@shared_task(bind=True)
def check_paper_plagiarism_task(self, paper_id: int) -> dict:

    try:
        paper = ResearchPaper.objects.get(id=paper_id)
    except ResearchPaper.DoesNotExist:
        logger.error("ResearchPaper %s not found for plagiarism check", paper_id)
        return {"status": "failed", "paper_id": paper_id, "error": "paper not found"}

    from_status = paper.status
    paper.status = ResearchPaper.Status.CHECKING_PLAGIARISM
    paper.save(update_fields=["status"])
    log_status_change(paper, from_status, paper.status, note="Automated plagiarism check started")

    raw_text = ""
    if paper.pdf_file:
        raw_text = extract_text_from_pdf(paper.pdf_file.path)
    if not raw_text.strip():
        raw_text = paper.abstract

    ai_keywords = []
    if AIKeywordExtractor is not None:
        try:
            ai_keywords = AIKeywordExtractor().extract_pure_keywords(raw_text, top_n=8)
        except Exception:
            logger.exception("Keyword extraction failed during plagiarism check for paper %s (non-blocking)", paper_id)

    internal_matches = []
    external_matches = []
    ai_error = None
    chunks, base_vectors = [], None

    if store_chunk_embeddings is None or find_internal_matches is None or run_external_check is None:
        ai_error = "Plagiarism detection services are not available."
    else:
        try:
            chunks, finetuned_vectors, base_vectors, language = store_chunk_embeddings(paper, raw_text)
            internal_matches = find_internal_matches(paper, chunks, finetuned_vectors, base_vectors, language)
        except Exception as e:
            ai_error = str(e)
            logger.exception("Internal plagiarism check failed for paper %s (non-blocking): %s", paper_id, e)

        try:
            external_matches = run_external_check(chunks, base_vectors, ai_keywords)
        except Exception as e:
            ai_error = ai_error or str(e)
            logger.exception("External plagiarism check failed for paper %s (non-blocking): %s", paper_id, e)

    # "مؤكَّد" هو ما يُحتسَب ضمن نسب التشابه الرسمية؛ "مشتبه به" (تشابه دلالي متوسط قد يكون
    # إعادة صياغة غير مكتشَفة حرفياً) لا يُحتسَب ضمن النسبة بل يُعرَض للمراجع البشري بشكل منفصل،
    # حلاً لضعف كشف إعادة الصياغة الحقيقية دون الحاجة لإعادة تدريب النموذج.
    confirmed_internal = [m for m in internal_matches if m.get("confidence_level") == "confirmed"]
    confirmed_external = [m for m in external_matches if m.get("confidence_level") == "confirmed"]
    suspected_internal = [m for m in internal_matches if m.get("confidence_level") == "suspected"]
    suspected_external = [m for m in external_matches if m.get("confidence_level") == "suspected"]

    internal_score = max([m["score"] for m in confirmed_internal], default=0.0) * 100
    external_score = max([m["score"] for m in confirmed_external], default=0.0) * 100
    total_score = max(internal_score, external_score)
    requires_human_review = bool((suspected_internal or suspected_external) and not (confirmed_internal or confirmed_external))

    PlagiarismReport.objects.filter(paper=paper).delete()
    report = PlagiarismReport.objects.create(
        paper=paper,
        status=PlagiarismReport.Status.SKIPPED if (not internal_matches and not external_matches and ai_error) else PlagiarismReport.Status.COMPLETED,
        total_similarity_score=total_score,
        internal_similarity_score=internal_score,
        external_similarity_score=external_score,
        requires_human_review=requires_human_review,
        ai_keywords=ai_keywords,
    )

    for match in internal_matches:
        PlagiarismSource.objects.create(
            report=report,
            source_type=PlagiarismSource.SourceType.INTERNAL,
            confidence_level=match.get("confidence_level", PlagiarismSource.ConfidenceLevel.CONFIRMED),
            matched_paper=match["matched_paper"],
            source_title=match["matched_paper"].title,
            match_percentage=match["score"] * 100,
            own_text_snippet=match["own_snippet"],
            source_text_snippet=match["source_snippet"],
        )

    for match in external_matches:
        PlagiarismSource.objects.create(
            report=report,
            source_type=PlagiarismSource.SourceType.EXTERNAL,
            confidence_level=match.get("confidence_level", PlagiarismSource.ConfidenceLevel.CONFIRMED),
            source_url=match["source_url"],
            source_title=match["source_title"],
            match_percentage=match["score"] * 100,
            own_text_snippet=match["own_snippet"],
            source_text_snippet=match["source_snippet"],
        )

    from_status = paper.status
    paper.status = ResearchPaper.Status.SUBMITTED
    paper.save(update_fields=["status"])
    note = (
        "Plagiarism check completed"
        if ai_error is None
        else f"Plagiarism AI check unavailable, proceeding without it: {ai_error}"
    )
    log_status_change(paper, from_status, paper.status, note=note)
    return {"status": paper.status, "paper_id": paper_id, "ai_check_ok": ai_error is None}

@shared_task(bind=True)
def compute_paper_embedding_task(self, paper_id: int) -> dict:
    try:
        paper = ResearchPaper.objects.get(id=paper_id)
    except ResearchPaper.DoesNotExist:
        logger.error("ResearchPaper %s not found for embedding computation", paper_id)
        return {"status": "failed", "paper_id": paper_id, "error": "paper not found"}

    if get_embedding_model is None or _paper_text is None:
        logger.warning("Embedding model unavailable; skipping paper embedding computation for paper %s", paper_id)
        return {"status": "skipped", "paper_id": paper_id}

    try:
        model = get_embedding_model()
        vector = model.encode([_paper_text(paper)])[0]
        PaperEmbedding.objects.update_or_create(
            paper=paper,
            defaults={"embedding_vector": vector.tolist()},
        )
    except Exception as e:
        logger.exception("Paper embedding computation failed for paper %s (non-blocking): %s", paper_id, e)
        return {"status": "failed", "paper_id": paper_id, "error": str(e)}

    return {"status": "completed", "paper_id": paper_id}
