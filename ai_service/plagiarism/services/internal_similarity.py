import numpy as np
from django.conf import settings
from sklearn.metrics.pairwise import cosine_similarity

from ai_service.utils.embeddings import get_embedding_model
from .chunking import chunk_text


def _embedding_model():
    return get_embedding_model(settings.PLAGIARISM_EMBEDDING_MODEL)


def store_chunk_embeddings(paper, raw_text):
    from research.models import PaperChunkEmbedding

    chunks = chunk_text(raw_text)
    PaperChunkEmbedding.objects.filter(paper=paper).delete()
    if not chunks:
        return [], None

    model = _embedding_model()
    vectors = model.encode(chunks)

    PaperChunkEmbedding.objects.bulk_create([
        PaperChunkEmbedding(
            paper=paper,
            chunk_index=index,
            chunk_text=chunk,
            embedding_vector=np.asarray(vector).tolist(),
        )
        for index, (chunk, vector) in enumerate(zip(chunks, vectors))
    ])
    return chunks, vectors


def find_internal_matches(paper, chunks, vectors):
    from research.models import PaperChunkEmbedding

    if vectors is None or len(chunks) == 0:
        return []

    threshold = getattr(settings, 'PLAGIARISM_INTERNAL_SIMILARITY_THRESHOLD', 0.75)

    others = (
        PaperChunkEmbedding.objects
        .exclude(paper_id=paper.id)
        .select_related('paper')
    )

    by_paper = {}
    for row in others:
        bucket = by_paper.setdefault(row.paper_id, {"paper": row.paper, "rows": []})
        bucket["rows"].append(row)

    matches = []
    for bucket in by_paper.values():
        other_vectors = np.array([r.embedding_vector for r in bucket["rows"]])
        scores = cosine_similarity(vectors, other_vectors)
        best_index = np.unravel_index(np.argmax(scores), scores.shape)
        best_score = float(scores[best_index])
        if best_score >= threshold:
            matches.append({
                "matched_paper": bucket["paper"],
                "score": best_score,
                "own_snippet": chunks[best_index[0]],
                "source_snippet": bucket["rows"][best_index[1]].chunk_text,
            })

    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches


def run_internal_check(paper, raw_text):
    chunks, vectors = store_chunk_embeddings(paper, raw_text)
    return find_internal_matches(paper, chunks, vectors)
