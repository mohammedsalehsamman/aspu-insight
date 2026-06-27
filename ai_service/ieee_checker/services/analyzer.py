from __future__ import annotations
import time
import logging
from typing import Any, Dict

from ..domain.entities import IEEECheckResult, ReferenceEntry
from ..infrastructure.file_parser import extract_text_from_file
from .citation_extractor import detect_language, extract_paper_title, extract_in_text_citations
from .reference_parser import find_references_section, split_references_section, parse_ieee_reference
from .format_validator import (
    validate_ieee_format,
    compute_ieee_score,
    calculate_scores,
    generate_recommendations,
    generate_summary,
)
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

    ref_map: Dict[int, ReferenceEntry] = {}
    crossref_calls = 0

    for ref_num, ref_text in raw_refs:
        parsed = parse_ieee_reference(ref_text)
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
        )

        entry.format_errors = validate_ieee_format(entry)
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

    result = calculate_scores(result)
    result.recommendations = generate_recommendations(result)
    result.summary = generate_summary(result)

    return result.to_dict()
