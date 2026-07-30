import re

from django.conf import settings

from ai_service.utils.nltk_setup import ensure_nltk_punkt

_FALLBACK_SENTENCE_SPLIT = re.compile(r'(?<=[.!?؟])\s+')

_QUOTE_MARK_RE = re.compile(r'["“”«»﴿﴾]')
_CITATION_MARKER_RE = re.compile(
    r'\[\d+(?:\s*,\s*\d+)*\]'                       # IEEE-style [3] or [3, 5]
    r'|\([^()]{0,40}(?:19|20)\d{2}\)'               # (Author, 2019) APA-style
    r'|\([؀-ۿ\s]{2,25}:\s*\d{1,3}\)'      # (سورة: آية) Quranic verse reference
    r'|et\s+al\.?'
    r'|نقلاً?\s+عن|كما\s+ورد\s+في|المصدر\s*:|بحسب\s+',
    re.IGNORECASE,
)
# نصوص قرآنية مُستخرَجة من PDF بخط قرآني (Uthmanic) تُحوَّل غالباً لرموز خاصة من نطاق "أشكال
# العرض العربية" (Arabic Presentation Forms) بدل الحروف العربية العادية — وجود عدة رموز من هذا
# النطاق في مقطع واحد إشارة شبه مؤكَّدة على أنه اقتباس قرآني منسوخ حرفياً من خط تنضيد، لا كتابة
# أصلية للباحث.
_QURANIC_LIGATURE_RE = re.compile(r'[ﭐ-﷿ﹰ-﻿]')
_QURANIC_LIGATURE_MIN_COUNT = 5


def is_citation_chunk(text):
    """True if this chunk is a directly-quoted, attributed citation (quotation marks
    plus an adjacent citation marker, or a verbatim Quranic-typeset excerpt) rather than
    the author's own original wording. Declared quotations of an external source are not
    plagiarism and must be excluded from internal-corpus similarity comparison, or shared
    reference material (statutes, scripture, clinical guidelines, textbook definitions)
    legitimately quoted verbatim by multiple independent papers produces false 'confirmed'
    matches between them."""
    if not text:
        return False
    if len(_QURANIC_LIGATURE_RE.findall(text)) >= _QURANIC_LIGATURE_MIN_COUNT:
        return True
    return bool(_QUOTE_MARK_RE.search(text) and _CITATION_MARKER_RE.search(text))


def _split_sentences(text):
    if ensure_nltk_punkt():
        try:
            import nltk
            return [s.strip() for s in nltk.sent_tokenize(text) if s.strip()]
        except Exception:
            pass
    return [s.strip() for s in _FALLBACK_SENTENCE_SPLIT.split(text) if s.strip()]


def chunk_text(text):
    text = (text or "").strip()
    if not text:
        return []

    sentences = _split_sentences(text)
    if not sentences:
        return []

    size = max(1, getattr(settings, 'PLAGIARISM_CHUNK_SENTENCES', 4))
    overlap = min(size - 1, max(0, getattr(settings, 'PLAGIARISM_CHUNK_OVERLAP', 1)))
    step = size - overlap

    chunks = []
    start = 0
    while start < len(sentences):
        window = sentences[start:start + size]
        if window:
            chunks.append(' '.join(window))
        if start + size >= len(sentences):
            break
        start += step
    return chunks
