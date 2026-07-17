from __future__ import annotations
import time
import logging
from typing import Any, Dict

from django.conf import settings

from ..domain.entities import IEEECheckResult, ReferenceEntry
from ..infrastructure.file_parser import extract_text_from_file
from .citation_extractor import detect_language, extract_paper_title, extract_in_text_citations
from .reference_parser import find_references_section, split_references_section
from .reference_extractor_ai import extract_reference_fields
from .format_validator_ai import validate_ieee_format_ai
from .format_validator import compute_ieee_score, calculate_scores
from .section_structure_checker import check_paper_structure
from .citation_semantic_matcher import find_citation_mismatches
from .recommendation_generator_ai import generate_recommendations_and_summary_ai
from .crossref_client import verify_doi

logger = logging.getLogger(__name__)

_MAX_FORMAT_ISSUES_SHOWN = 20


def perform_ieee_analysis(
    file_path: str,
    verify_crossref: bool = True,
    max_crossref_calls: int = 5,
) -> Dict[str, Any]:

    result = IEEECheckResult()

    full_text, page_count, _ = extract_text_from_file(file_path)
    result.total_pages = page_count

    if not full_text.strip():
        result.summary = "تعذّر استخراج النص من الملف. تأكد أن الـ PDF يحتوي على نص قابل للبحث."
        result.status = "fail"
        result.recommendations = ["تحويل الـ PDF إلى صيغة نصية أو استخدام OCR."]
        return result.to_dict()

    result.paper_title = extract_paper_title(full_text)
    result.detected_language = detect_language(full_text)

    citation_counts = extract_in_text_citations(full_text)
    result.citations_in_text = sorted(citation_counts.keys())

    ref_section = find_references_section(full_text)
    raw_refs = split_references_section(ref_section) if ref_section else []

    max_llm_refs = getattr(settings, "IEEE_CHECKER_MAX_LLM_REFS", 30)

    ref_map: Dict[int, ReferenceEntry] = {}
    crossref_calls = 0

    for i, (ref_num, ref_text) in enumerate(raw_refs):
        if i < max_llm_refs:
            parsed = extract_reference_fields(ref_text)
        else:
            from .reference_parser import parse_ieee_reference
            parsed = parse_ieee_reference(ref_text)
            parsed['extraction_method'] = "regex_fallback"
            parsed['extraction_confidence'] = 0.0

        entry = ReferenceEntry(
            index=ref_num,
            raw_text=ref_text[:300],
            authors=parsed['authors'],
            title=parsed['title'],
            source=parsed['source'],
            year=parsed['year'],
            doi=parsed['doi'],
            url=parsed['url'],
            volume=parsed['volume'],
            issue=parsed['issue'],
            pages=parsed['pages'],
            extraction_method=parsed.get('extraction_method', 'regex_fallback'),
            extraction_confidence=parsed.get('extraction_confidence', 0.0),
        )

        entry.format_errors = validate_ieee_format_ai(entry)
        entry.ieee_score = compute_ieee_score(entry.format_errors)

        if verify_crossref and entry.doi and crossref_calls < max_crossref_calls:
            is_valid, msg = verify_doi(entry.doi)
            entry.crossref_verified = is_valid
            entry.crossref_message = msg
            crossref_calls += 1
            result.crossref_checked += 1
            if is_valid:
                result.crossref_verified_count += 1
            else:
                result.crossref_failed.append(ref_num)
            time.sleep(0.3)

        if ref_num not in ref_map:
            ref_map[ref_num] = entry

    result.references = list(ref_map.values())
    result.total_references = len(ref_map)
    ref_ids = set(ref_map.keys())

    cited_set = set(result.citations_in_text)
    result.citations_missing_from_references = sorted(cited_set - ref_ids)
    result.unused_references = sorted(ref_ids - cited_set)

    for ref in result.references:
        joined_errors = " ".join(ref.format_errors)
        if "سنة" in joined_errors:
            result.references_without_year.append(ref.index)
        if "المؤلف" in joined_errors:
            result.references_without_authors.append(ref.index)
        if "عنوان" in joined_errors:
            result.references_without_title.append(ref.index)

    all_format_errors = [
        f"[{ref.index}]: {err}"
        for ref in result.references
        for err in ref.format_errors
    ]
    result.format_issues_summary = all_format_errors[:_MAX_FORMAT_ISSUES_SHOWN]
    if len(all_format_errors) > _MAX_FORMAT_ISSUES_SHOWN:
        result.format_issues_summary.append(
            f"... و {len(all_format_errors) - _MAX_FORMAT_ISSUES_SHOWN} مشكلة إضافية"
        )

    structure = check_paper_structure(full_text)
    result.detected_sections = structure['detected_sections']
    result.missing_required_sections = structure['missing_required_sections']
    result.section_order_valid = structure['section_order_valid']
    result.structure_score = structure['structure_score']

    result.citation_mismatches = find_citation_mismatches(
        full_text, result.citations_in_text, result.references
    )

    result = calculate_scores(result)
    result.summary, result.recommendations = generate_recommendations_and_summary_ai(result)

    return result.to_dict()
