import numpy as np
from django.conf import settings
from sklearn.metrics.pairwise import cosine_similarity

from ai_service.utils.embeddings import get_embedding_model
from ai_service.ieee_checker.services.citation_extractor import detect_language
from .chunking import chunk_text, is_citation_chunk


def _finetuned_model():
    return get_embedding_model(settings.PLAGIARISM_EMBEDDING_MODEL)


def _base_model():
    return get_embedding_model(settings.PLAGIARISM_BASE_EMBEDDING_MODEL)


def store_chunk_embeddings(paper, raw_text):
    from research.models import PaperChunkEmbedding

    chunks = chunk_text(raw_text)
    PaperChunkEmbedding.objects.filter(paper=paper).delete()
    if not chunks:
        return [], None, None, "unknown"

    language = detect_language(raw_text)
    finetuned_vectors = _finetuned_model().encode(chunks)
    base_vectors = _base_model().encode(chunks)

    PaperChunkEmbedding.objects.bulk_create([
        PaperChunkEmbedding(
            paper=paper,
            chunk_index=index,
            chunk_text=chunk,
            embedding_vector=np.asarray(ft_vector).tolist(),
            base_embedding_vector=np.asarray(base_vector).tolist(),
            detected_language=language,
            is_citation=is_citation_chunk(chunk),
        )
        for index, (chunk, ft_vector, base_vector) in enumerate(zip(chunks, finetuned_vectors, base_vectors))
    ])
    return chunks, finetuned_vectors, base_vectors, language


def find_internal_matches(paper, chunks, finetuned_vectors, base_vectors, language):
    from research.models import PaperChunkEmbedding

    if finetuned_vectors is None or len(chunks) == 0:
        return []

    threshold = getattr(settings, 'PLAGIARISM_INTERNAL_SIMILARITY_THRESHOLD', 0.75)
    suspected_threshold = getattr(settings, 'PLAGIARISM_SUSPECTED_INTERNAL_THRESHOLD', 0.30)
    corroboration_threshold = getattr(settings, 'PLAGIARISM_CORROBORATION_THRESHOLD', 0.50)
    min_corroborating_chunks = getattr(settings, 'PLAGIARISM_MIN_CORROBORATING_CHUNKS', 2)

    # اقتباس مُصرَّح به (علامات تنصيص + إشارة استشهاد) ليس انتحالاً — نصوص مرجعية مشتركة (نصوص
    # دينية/كلاسيكية، مواد قانونية، تعريفات طبية معيارية) يقتبسها أكثر من بحث مستقل بشكل مشروع
    # تماماً، وهذا تسبَّب تجريبياً بنسبة اتهام كاذب مرتفعة جداً على مستوى الورقة الكاملة (دراسة
    # rigor_gap_coverage_study.py). تُستبعَد هذه المقاطع من المقارنة على جانبَي الورقتين معاً.
    own_citation_mask = [is_citation_chunk(c) for c in chunks]
    own_indices = [i for i, is_cite in enumerate(own_citation_mask) if not is_cite]
    if not own_indices:
        return []
    filtered_chunks = [chunks[i] for i in own_indices]
    finetuned_vectors = np.array(finetuned_vectors)[own_indices]
    base_vectors = np.array(base_vectors)[own_indices]

    others = (
        PaperChunkEmbedding.objects
        .exclude(paper_id=paper.id)
        .exclude(is_citation=True)
        .select_related('paper')
    )

    by_paper = {}
    for row in others:
        bucket = by_paper.setdefault(row.paper_id, {"paper": row.paper, "rows": []})
        bucket["rows"].append(row)

    matches = []
    for bucket in by_paper.values():
        rows = bucket["rows"]
        other_language = rows[0].detected_language

        # مقارنة عربي-عربي تستخدم الموديل المُضبَط دقيقاً (الأفضل هنا)؛ أي مقارنة عابرة
        # للغات (أو لغة غير مكتشَفة) تستخدم الموديل الأساس المشترك، لأن المقارنة بين متجهين
        # من موديلين مختلفين غير صحيحة رياضياً (فضاءان مختلفان تماماً).
        if language == "ar" and other_language == "ar":
            own_vectors = finetuned_vectors
            usable_rows = [r for r in rows if r.embedding_vector is not None]
            other_vectors = [r.embedding_vector for r in usable_rows]
        else:
            own_vectors = base_vectors
            usable_rows = [r for r in rows if r.base_embedding_vector is not None]
            other_vectors = [r.base_embedding_vector for r in usable_rows]

        if not other_vectors:
            # بحث آخر لم تُحسَب له بعد المتجهات اللازمة لهذه المقارنة تحديداً (بيانات قديمة
            # قبل إضافة هذا الحقل، أو لم يُعالَج بعد) — يُتجاوَز بأمان بدل الانهيار.
            continue

        other_vectors = np.array(other_vectors)
        scores = cosine_similarity(own_vectors, other_vectors)
        best_index = np.unravel_index(np.argmax(scores), scores.shape)
        best_score = float(scores[best_index])
        if best_score >= suspected_threshold:
            # مطابقة واحدة معزولة بين عشرات مقاطع ورقتين كاملتين قد تحدث صدفة (مفردات أكاديمية
            # مشتركة بنفس التخصص) حتى لو كانت الورقتان غير مرتبطتين إطلاقاً — تأكَّد هذا تجريبياً
            # (دراسة rigor_gap_coverage_study.py). لذلك "التأكيد" يتطلب دليلاً داعماً من أكثر من
            # مقطع مستقل يطابق نفس الورقة الأخرى، لا أعلى قيمة واحدة فقط مهما علت — إلا إذا كانت
            # الورقة نفسها قصيرة جداً (أقل من الحد الأدنى من المقاطع) فلا معنى لطلب تعدد الأدلة.
            if len(own_vectors) < min_corroborating_chunks:
                corroborating_chunks = 1 if best_score >= threshold else 0
                is_confirmed = best_score >= threshold
            else:
                row_best = scores.max(axis=1)
                corroborating_chunks = int((row_best >= corroboration_threshold).sum())
                is_confirmed = best_score >= threshold and corroborating_chunks >= min_corroborating_chunks
            matches.append({
                "matched_paper": bucket["paper"],
                "score": best_score,
                "confidence_level": "confirmed" if is_confirmed else "suspected",
                "corroborating_chunks": corroborating_chunks,
                "own_snippet": filtered_chunks[best_index[0]],
                "source_snippet": usable_rows[best_index[1]].chunk_text,
            })

    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches


def run_internal_check(paper, raw_text):
    chunks, finetuned_vectors, base_vectors, language = store_chunk_embeddings(paper, raw_text)
    return find_internal_matches(paper, chunks, finetuned_vectors, base_vectors, language)
