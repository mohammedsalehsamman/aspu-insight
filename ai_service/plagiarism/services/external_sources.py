import io
import logging
import time

import numpy as np
import requests
from django.conf import settings
from pypdf import PdfReader
from sklearn.metrics.pairwise import cosine_similarity

from ai_service.utils.embeddings import get_embedding_model

logger = logging.getLogger(__name__)


def _embedding_model():
    # الموديل الأساس دوماً هنا (وليس المُضبَط دقيقاً للعربية) لأن المقارنة الخارجية
    # عابرة للغات بطبيعتها (بحث قد يكون عربياً مقابل مصادر إنجليزية غالباً).
    return get_embedding_model(settings.PLAGIARISM_BASE_EMBEDDING_MODEL)


def _best_match_against_chunks(chunks, vectors, candidate_text, source_excerpt_len=800):
    candidate_text = (candidate_text or "").strip()
    if not candidate_text:
        return 0.0, "", ""

    model = _embedding_model()
    candidate_vector = model.encode([candidate_text])
    scores = cosine_similarity(vectors, candidate_vector).flatten()
    best_index = int(np.argmax(scores))
    own_snippet = chunks[best_index]
    source_snippet = candidate_text[:source_excerpt_len]
    return float(scores[best_index]), own_snippet, source_snippet


def _extract_pdf_text_from_url(url, max_chars=5000, timeout=8, max_pages=5):
    if not url:
        return None
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        reader = PdfReader(io.BytesIO(response.content))
        text = ""
        for page in reader.pages[:max_pages]:
            page_text = page.extract_text()
            if page_text:
                text += page_text + " "
            if len(text) >= max_chars:
                break
        text = text.strip()
        return text[:max_chars] if text else None
    except Exception:
        logger.exception("Could not fetch/parse open-access PDF for full-text comparison (non-blocking)")
        return None


def search_semantic_scholar(keywords, chunks, vectors, limit=3):
    query = " ".join((keywords or [])[:5]).strip()
    if not query or not chunks:
        return []

    try:
        response = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": query, "limit": limit, "fields": "title,url,abstract,openAccessPdf"},
            timeout=5,
        )
        response.raise_for_status()
        papers = response.json().get("data", [])
    except requests.RequestException:
        logger.exception("Semantic Scholar search failed (non-blocking)")
        return []

    threshold = getattr(settings, 'PLAGIARISM_EXTERNAL_SIMILARITY_THRESHOLD', 0.6)
    results = []
    for paper_data in papers:
        # نفضّل مقارنة النص الكامل للبحث المفتوح الوصول عند توفره؛ الملخص فقط بديل احتياطي
        open_access = paper_data.get("openAccessPdf") or {}
        pdf_url = open_access.get("url") if isinstance(open_access, dict) else None
        candidate_text = _extract_pdf_text_from_url(pdf_url) or paper_data.get("abstract")

        score, own_snippet, source_snippet = _best_match_against_chunks(chunks, vectors, candidate_text)
        if score >= threshold:
            results.append({
                "source_url": paper_data.get("url", "") or "",
                "source_title": paper_data.get("title", "") or "",
                "score": score,
                "own_snippet": own_snippet,
                "source_snippet": source_snippet,
            })
    return results


def search_core(keywords, chunks, vectors, limit=3):
    api_key = getattr(settings, 'CORE_API_KEY', '')
    query = " ".join((keywords or [])[:5]).strip()
    if not api_key or not query or not chunks:
        return []

    try:
        response = requests.get(
            "https://api.core.ac.uk/v3/search/works",
            params={"q": query, "limit": limit},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=8,
        )
        response.raise_for_status()
        works = response.json().get("results", [])
    except requests.RequestException:
        logger.exception("CORE API search failed (non-blocking)")
        return []

    threshold = getattr(settings, 'PLAGIARISM_EXTERNAL_SIMILARITY_THRESHOLD', 0.6)
    results = []
    for work in works:
        # CORE يوفّر أحياناً النص الكامل مباشرة في الاستجابة، دون الحاجة لتنزيل PDF منفصل
        candidate_text = work.get("fullText") or work.get("abstract")
        score, own_snippet, source_snippet = _best_match_against_chunks(chunks, vectors, candidate_text)
        if score >= threshold:
            source_url = work.get("downloadUrl") or ""
            results.append({
                "source_url": source_url,
                "source_title": work.get("title", "") or "",
                "score": score,
                "own_snippet": own_snippet,
                "source_snippet": source_snippet,
            })
    return results


def search_valueserp(chunks, vectors):
    api_key = getattr(settings, 'VALUESERP_API_KEY', '')
    if not api_key or not chunks:
        return []

    threshold = getattr(settings, 'PLAGIARISM_EXTERNAL_SIMILARITY_THRESHOLD', 0.6)
    model = _embedding_model()
    results = []

    for chunk, chunk_vector in zip(chunks, vectors):
        try:
            response = requests.get(
                "https://api.valueserp.com/search",
                params={"api_key": api_key, "q": chunk, "search_type": "scholar"},
                timeout=10,
            )
            response.raise_for_status()
            organic_results = response.json().get("organic_results", [])
        except requests.RequestException:
            logger.exception("ValueSerp search failed for a chunk (non-blocking)")
            continue

        for item in organic_results:
            snippet = (item.get("snippet") or "").strip()
            if not snippet:
                continue
            snippet_vector = model.encode([snippet])
            score = float(cosine_similarity([chunk_vector], snippet_vector)[0][0])
            if score >= threshold:
                results.append({
                    "source_url": item.get("link", "") or "",
                    "source_title": item.get("title", "") or "",
                    "score": score,
                    "own_snippet": chunk,
                    "source_snippet": snippet,
                })
        time.sleep(0.2)

    return results


def run_external_check(chunks, vectors, keywords):
    if vectors is None or not chunks:
        return []
    results = []
    results.extend(search_semantic_scholar(keywords, chunks, vectors))
    results.extend(search_core(keywords, chunks, vectors))
    results.extend(search_valueserp(chunks, vectors))
    return results
