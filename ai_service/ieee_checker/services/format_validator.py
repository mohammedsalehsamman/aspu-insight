from __future__ import annotations
import re
from typing import List

from ..domain.entities import IEEECheckResult, ReferenceEntry

_PENALTY_MAP = {
    "المؤلف": 25,
    "عنوان": 25,
    "سنة": 20,
    "المجلة": 15,
    "DOI": 10,
    "صفحات": 5,
}


def validate_ieee_format(ref: ReferenceEntry) -> List[str]:
    errors: List[str] = []

    if not ref.authors:
        errors.append("مفقود: اسم المؤلف/المؤلفين")
    else:
        arabic_count = len(re.findall(r'[؀-ۿ]', ref.authors))
        if arabic_count == 0 and not re.search(r'[A-Z]\.\s*[A-Z][a-z]', ref.authors):
            errors.append("تنسيق المؤلفين: يُفضَّل النمط IEEE (الحرف.الأول الاسمُ الأخير)")

    if not ref.title:
        errors.append('مفقود: عنوان البحث (يجب بين علامتي اقتباس "...")')

    if not ref.year:
        errors.append("مفقودة: سنة النشر")
    elif not re.match(r'^(19|20)\d{2}$', ref.year):
        errors.append(f"سنة النشر غير صحيحة: {ref.year}")

    if not ref.source and not ref.url:
        errors.append("مفقود: اسم المجلة أو المؤتمر أو الناشر")

    if ref.doi and not re.match(r'^10\.\d{4,}/', ref.doi):
        errors.append(f"تنسيق DOI غير صحيح: {ref.doi}")

    if not ref.pages and not ref.url and ref.source:
        errors.append("يُنصح: إضافة أرقام الصفحات (pp. X-Y)")

    return errors


def compute_ieee_score(format_errors: List[str]) -> float:
    penalty = 0
    for err in format_errors:
        for key, val in _PENALTY_MAP.items():
            if key in err:
                penalty += val
                break
        else:
            penalty += 10
    return max(0.0, 100.0 - penalty)


def calculate_scores(result: IEEECheckResult) -> IEEECheckResult:
    total_cited = len(result.citations_in_text)
    missing = len(result.citations_missing_from_references)
    unused = len(result.unused_references)

    if total_cited == 0 and result.total_references == 0:
        result.citation_matching_score = 100.0
    elif total_cited == 0:
        result.citation_matching_score = 50.0
    else:
        penalty = (missing * 10) + (unused * 5)
        result.citation_matching_score = max(0.0, 100.0 - penalty)

    if result.total_references == 0:
        result.format_score = 0.0
    else:
        total_errors = sum(len(ref.format_errors) for ref in result.references)
        avg_errors = total_errors / result.total_references
        result.format_score = max(0.0, 100.0 - (avg_errors * 15))

    if result.crossref_checked == 0:
        result.crossref_score = 0.0
        result.overall_score = round(
            result.citation_matching_score * 0.50
            + result.format_score * 0.50,
            1,
        )
    else:
        result.crossref_score = (result.crossref_verified_count / result.crossref_checked) * 100.0
        result.overall_score = round(
            result.citation_matching_score * 0.40
            + result.format_score * 0.40
            + result.crossref_score * 0.20,
            1,
        )

    if result.overall_score >= 75:
        result.status = "pass"
    elif result.overall_score >= 50:
        result.status = "warning"
    else:
        result.status = "fail"

    return result


def generate_recommendations(result: IEEECheckResult) -> List[str]:
    recs: List[str] = []

    if result.citations_missing_from_references:
        nums = ", ".join(f"[{n}]" for n in sorted(result.citations_missing_from_references))
        recs.append(f"أضف المراجع المفقودة لهذه الاستشهادات: {nums}")

    if result.unused_references:
        nums = ", ".join(f"[{n}]" for n in sorted(result.unused_references))
        recs.append(f"المراجع غير المُستشهَد بها: {nums} — احذفها أو أضف استشهادات لها في النص")

    if result.references_without_year:
        nums = ", ".join(f"[{n}]" for n in sorted(result.references_without_year)[:5])
        recs.append(f"أضف سنة النشر للمراجع: {nums}")

    if result.references_without_authors:
        nums = ", ".join(f"[{n}]" for n in sorted(result.references_without_authors)[:5])
        recs.append(f"أضف أسماء المؤلفين للمراجع: {nums}")

    if result.references_without_title:
        nums = ", ".join(f"[{n}]" for n in sorted(result.references_without_title)[:5])
        recs.append(f"أضف عنوان البحث بين علامتي اقتباس للمراجع: {nums}")

    if result.crossref_failed:
        nums = ", ".join(f"[{n}]" for n in sorted(result.crossref_failed)[:3])
        recs.append(f"تحقق يدوياً من صحة DOI في المراجع: {nums}")

    if result.format_score < 60:
        recs.append(
            'راجع تنسيق IEEE العام: المؤلف (الحرف.الأول الاسم)، '
            '"العنوان," المجلة، vol. X, no. Y, pp. Z-W, السنة.'
        )

    if not recs:
        recs.append("ممتاز! لا توجد مشكلات جوهرية في الاستشهادات والمراجع.")

    return recs


def generate_summary(result: IEEECheckResult) -> str:
    status_ar = {
        "pass": "مقبول",
        "warning": "يحتاج تحسين",
        "fail": "يحتاج مراجعة جوهرية",
    }.get(result.status, "غير محدد")

    return (
        f'الورقة: "{result.paper_title[:60]}" | '
        f"اللغة: {result.detected_language} | "
        f"الصفحات: {result.total_pages} | "
        f"الاستشهادات في النص: {len(result.citations_in_text)} | "
        f"إجمالي المراجع: {result.total_references} | "
        f"الدرجة: {result.overall_score}/100 | "
        f"الحالة: {status_ar}"
    )
