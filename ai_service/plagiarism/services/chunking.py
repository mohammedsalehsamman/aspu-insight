import re

from django.conf import settings

from ai_service.utils.nltk_setup import ensure_nltk_punkt

_FALLBACK_SENTENCE_SPLIT = re.compile(r'(?<=[.!?؟])\s+')


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
