import logging

import numpy as np

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.2

def _paper_text(paper):
    parts = [paper.title or "", paper.abstract or "", paper.specialization or ""]
    return " ".join(p.strip() for p in parts if p and p.strip())


def _vectors_for_papers(papers, model):
    from research.models import PaperEmbedding

    precomputed = {
        row.paper_id: np.asarray(row.embedding_vector)
        for row in PaperEmbedding.objects.filter(paper__in=papers)
    }

    missing = [p for p in papers if p.id not in precomputed]
    if missing:
        fresh_vectors = model.encode([_paper_text(p) for p in missing])
        for paper, vector in zip(missing, fresh_vectors):
            precomputed[paper.id] = np.asarray(vector)

    return np.array([precomputed[p.id] for p in papers])


class AIPaperSearchService:

    @staticmethod
    def semantic_search(query, papers_queryset, top_n=20):
        query_text = (query or "").strip()
        papers = list(papers_queryset)
        if not query_text or not papers:
            return []

        try:
            from sklearn.metrics.pairwise import cosine_similarity
            from ai_service.utils.embeddings import get_embedding_model

            model = get_embedding_model()
            query_vector = model.encode([query_text])
            paper_vectors = _vectors_for_papers(papers, model)
            scores = cosine_similarity(query_vector, paper_vectors).flatten()
        except Exception:
            logger.exception("Semantic search embedding unavailable; falling back to plain text matching.")
            q_lower = query_text.lower()
            return [p for p in papers if q_lower in _paper_text(p).lower()][:top_n]

        ranked = sorted(zip(papers, scores), key=lambda item: item[1], reverse=True)
        return [paper for paper, score in ranked if score >= SIMILARITY_THRESHOLD][:top_n]

    @staticmethod
    def recommend_similar_papers(paper, candidates_queryset, top_n=5):
        candidates = [p for p in candidates_queryset if p.id != paper.id]
        if not candidates:
            return []

        try:
            from sklearn.metrics.pairwise import cosine_similarity
            from ai_service.utils.embeddings import get_embedding_model

            model = get_embedding_model()
            target_vector = _vectors_for_papers([paper], model)
            candidate_vectors = _vectors_for_papers(candidates, model)
            scores = cosine_similarity(target_vector, candidate_vectors).flatten()
        except Exception:
            logger.exception("Recommendation embedding unavailable; falling back to same-specialization match.")
            if not paper.specialization:
                return []
            return [p for p in candidates if p.specialization == paper.specialization][:top_n]

        ranked = sorted(zip(candidates, scores), key=lambda item: item[1], reverse=True)
        return [candidate for candidate, score in ranked if score >= SIMILARITY_THRESHOLD][:top_n]
