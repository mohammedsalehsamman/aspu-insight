from __future__ import annotations

import re

CLAIM_CUES = [
    "we propose", "we argue", "we claim", "we hypothesize", "we believe",
    "this suggests", "this indicates", "this implies", "we contend",
    "our approach", "we present", "we introduce", "this paper proposes",
    "we assume", "it is likely that", "we expect", "should be considered",
    "we recommend", "this demonstrates the need", "in our view",
]

EVIDENCE_CUES = [
    "results show", "results indicate", "as shown in table", "as shown in figure",
    "figure", "table", "as illustrated in", "the data show", "experiments show",
    "we observed", "we found that", "according to the results",
    "the experiment demonstrates", "as depicted in", "p <", "p-value",
    "statistically significant", "% of", "percent", "increase of", "decrease of",
    "compared to", "outperform", "accuracy of", "correlation",
]

CLAIM_CUES_AR = [
    "نقترح", "نرى أن", "نرى أنّ", "تشير هذه النتائج إلى", "نفترض", "نوصي بـ",
    "نوصي ب", "يقترح الباحث", "تقترح هذه الدراسة", "نعتقد أن", "نعتقد أنّ",
    "من المتوقع أن", "من المرجح أن", "تشير الدراسة إلى", "يشير هذا إلى",
    "هذا يدل على", "تدعو الحاجة إلى", "في رأينا",
]

EVIDENCE_CUES_AR = [
    "أظهرت النتائج", "أظهرت الدراسة", "كما هو موضح في الجدول", "كما هو موضح في الشكل",
    "الجدول", "الشكل", "بنسبة", "أشارت البيانات إلى", "أوضحت النتائج",
    "وفقاً للنتائج", "وفقًا للنتائج", "لاحظنا أن", "لاحظنا أنّ", "وجدنا أن", "وجدنا أنّ",
    "بلغت نسبة", "ارتفاع", "انخفاض", "مقارنة بـ", "دلالة إحصائية", "معامل الارتباط",
]

_NUMERIC_RE = re.compile(r'\b\d+(\.\d+)?\s*(%|percent)\b', re.IGNORECASE)
_TABLE_FIGURE_RE = re.compile(r'\b(table|figure|fig\.)\s*\d+\b', re.IGNORECASE)

_NUMERIC_RE_AR = re.compile(r'[\d٠-٩]+([.,][\d٠-٩]+)?\s*(%|٪|بالمئة|بالمائة)')
_TABLE_FIGURE_RE_AR = re.compile(r'(الجدول|الشكل)\s*[\d٠-٩]+')

def score_sentence_heuristic(sentence: str) -> tuple[str, float]:
    text_lower = sentence.lower()

    evidence_score = sum(1 for cue in EVIDENCE_CUES + EVIDENCE_CUES_AR if cue in text_lower)
    claim_score = sum(1 for cue in CLAIM_CUES + CLAIM_CUES_AR if cue in text_lower)

    if _TABLE_FIGURE_RE.search(sentence) or _TABLE_FIGURE_RE_AR.search(sentence):
        evidence_score += 2
    if _NUMERIC_RE.search(sentence) or _NUMERIC_RE_AR.search(sentence):
        evidence_score += 1

    if evidence_score == 0 and claim_score == 0:
        return "neutral", 0.0

    if evidence_score > claim_score:
        return "evidence", min(0.3, 0.1 * evidence_score)
    if claim_score > evidence_score:
        return "claim", min(0.3, 0.1 * claim_score)

    return "neutral", 0.0
