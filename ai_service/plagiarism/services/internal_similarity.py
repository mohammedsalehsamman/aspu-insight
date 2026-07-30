import os
from functools import lru_cache

import numpy as np
from django.conf import settings
from sklearn.metrics.pairwise import cosine_similarity

from ai_service.utils.embeddings import get_embedding_model
from ai_service.ieee_checker.services.citation_extractor import detect_language
from .chunking import chunk_text, is_citation_chunk
from .section_extractor import extract_core_sections


def _finetuned_model():
    return get_embedding_model(settings.PLAGIARISM_EMBEDDING_MODEL)


def _base_model():
    return get_embedding_model(settings.PLAGIARISM_BASE_EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def _bootstrap_commonness_reference():
    """ملف ثابت مبني مسبقاً من ARPD (انظر build_commonness_reference.py) — يمنح ميزة الترجيح
    العكسي بيانات تعمل عليها منذ أول انطلاقة للمجلة قبل توفر عدد كافٍ من أبحاثها الحقيقية."""
    path = getattr(settings, 'PLAGIARISM_COMMONNESS_REFERENCE_PATH', '')
    if not path or not os.path.exists(path):
        return np.zeros((0, 384), dtype=np.float32)
    return np.load(path)


def _commonness_count(vector, reference_vectors, threshold):
    if reference_vectors is None or len(reference_vectors) == 0:
        return 0
    sims = cosine_similarity(np.asarray(vector).reshape(1, -1), reference_vectors)[0]
    return int((sims >= threshold).sum())


def store_chunk_embeddings(paper, raw_text):
    from research.models import PaperChunkEmbedding

    # اقتصار المقارنة الداخلية على جوهر البحث العلمي فقط (الملخص، النتائج، المنهجية/الخوارزميات
    # المستخدَمة) لا النص الكامل — تأكَّد تجريبياً أن مقارنة النص الكامل (بما فيه الإهداء والشكر
    # والمقدمات العامة) تُنتج تطابقات كاذبة مرتفعة جداً حتى بين أوراق حقيقية مستقلة تماماً لا
    # علاقة بينها إطلاقاً (محاسبة مقابل طب، 96.5% "مؤكَّد" في اختبار فعلي).
    core_text = extract_core_sections(raw_text)
    chunks = chunk_text(core_text)
    PaperChunkEmbedding.objects.filter(paper=paper).delete()
    if not chunks:
        return [], None, None, []

    # كشف اللغة لكل مقطع على حدة، لا للورقة كاملة مرة واحدة — ورقة "عربية" بمجملها قد تحوي
    # مقاطع إنجليزية (ملخص مترجَم شائع في جامعات المغرب العربي مثلاً)، ومقارنتها بالموديل
    # العربي المُضبَط دقيقاً بدل الموديل الأساس تُنتج تشابهاً غير موثوق (تأكَّد تجريبياً: مقطع
    # عن ضغوط التمريض تطابق 0.52 مع نص قانوني إنجليزي لمجرد أن كلا الورقتين "عربيتان" إجمالاً).
    chunk_languages = [detect_language(c) for c in chunks]
    finetuned_vectors = _finetuned_model().encode(chunks)
    base_vectors = _base_model().encode(chunks)

    PaperChunkEmbedding.objects.bulk_create([
        PaperChunkEmbedding(
            paper=paper,
            chunk_index=index,
            chunk_text=chunk,
            embedding_vector=np.asarray(ft_vector).tolist(),
            base_embedding_vector=np.asarray(base_vector).tolist(),
            detected_language=chunk_lang,
            is_citation=is_citation_chunk(chunk),
        )
        for index, (chunk, ft_vector, base_vector, chunk_lang) in enumerate(
            zip(chunks, finetuned_vectors, base_vectors, chunk_languages)
        )
    ])
    return chunks, finetuned_vectors, base_vectors, chunk_languages


def find_internal_matches(paper, chunks, finetuned_vectors, base_vectors, chunk_languages):
    from research.models import PaperChunkEmbedding

    if finetuned_vectors is None or len(chunks) == 0:
        return []

    threshold = getattr(settings, 'PLAGIARISM_INTERNAL_SIMILARITY_THRESHOLD', 0.75)
    suspected_threshold = getattr(settings, 'PLAGIARISM_SUSPECTED_INTERNAL_THRESHOLD', 0.30)
    corroboration_threshold = getattr(settings, 'PLAGIARISM_CORROBORATION_THRESHOLD', 0.50)
    min_corroborating_chunks = getattr(settings, 'PLAGIARISM_MIN_CORROBORATING_CHUNKS', 2)
    commonness_threshold = getattr(settings, 'PLAGIARISM_COMMONNESS_THRESHOLD', 0.60)
    commonness_max_count = getattr(settings, 'PLAGIARISM_COMMONNESS_MAX_COUNT', 5)

    # اقتباس مُصرَّح به (علامات تنصيص + إشارة استشهاد) ليس انتحالاً — نصوص مرجعية مشتركة (نصوص
    # دينية/كلاسيكية، مواد قانونية، تعريفات طبية معيارية) يقتبسها أكثر من بحث مستقل بشكل مشروع
    # تماماً، وهذا تسبَّب تجريبياً بنسبة اتهام كاذب مرتفعة جداً على مستوى الورقة الكاملة (دراسة
    # rigor_gap_coverage_study.py). تُستبعَد هذه المقاطع من المقارنة على جانبَي الورقتين معاً.
    own_citation_mask = [is_citation_chunk(c) for c in chunks]
    own_indices = [i for i, is_cite in enumerate(own_citation_mask) if not is_cite]
    if not own_indices:
        return []
    filtered_chunks = [chunks[i] for i in own_indices]
    filtered_languages = [chunk_languages[i] for i in own_indices]
    finetuned_vectors = np.array(finetuned_vectors)[own_indices]
    base_vectors = np.array(base_vectors)[own_indices]
    own_is_ar = np.array([lang == "ar" for lang in filtered_languages])

    others = list(
        PaperChunkEmbedding.objects
        .exclude(paper_id=paper.id)
        .exclude(is_citation=True)
        .select_related('paper')
    )

    # مكتبة "الترجيح العكسي" الحيّة: كل مقاطع كل الأبحاث الأخرى المُخزَّنة فعلياً في المنصة، مجمَّعة
    # بلا تقسيم حسب الورقة — تُستخدَم لقياس مدى شيوع صياغة مقطع مُعيَّن عبر المكتبة كاملة، لا فقط
    # مع الورقة المُقارَنة تحديداً. تنمو تلقائياً مع كل بحث جديد يُرفَع، بلا حاجة لإعادة بناء يدوي.
    live_finetuned_pool = np.array([r.embedding_vector for r in others if r.embedding_vector is not None])
    live_base_pool = np.array([r.base_embedding_vector for r in others if r.base_embedding_vector is not None])
    bootstrap_pool = _bootstrap_commonness_reference()

    by_paper = {}
    for row in others:
        bucket = by_paper.setdefault(row.paper_id, {"paper": row.paper, "rows": []})
        bucket["rows"].append(row)

    matches = []
    for bucket in by_paper.values():
        rows = bucket["rows"]
        usable_rows = [r for r in rows if r.embedding_vector is not None and r.base_embedding_vector is not None]
        if not usable_rows:
            # بحث آخر لم تُحسَب له بعد المتجهات اللازمة لهذه المقارنة تحديداً (بيانات قديمة
            # قبل إضافة هذا الحقل، أو لم يُعالَج بعد) — يُتجاوَز بأمان بدل الانهيار.
            continue

        other_finetuned = np.array([r.embedding_vector for r in usable_rows])
        other_base = np.array([r.base_embedding_vector for r in usable_rows])
        other_is_ar = np.array([r.detected_language == "ar" for r in usable_rows])

        # اختيار الموديل الصحيح لكل زوج مقطعين على حدة، لا لكل ورقة ككل: عربي-عربي يستخدم
        # الموديل المُضبَط دقيقاً (الأفضل هنا)؛ أي مزيج آخر (حتى داخل ورقتين "عربيتين" إجمالاً،
        # قد يحوي أحدهما مقطعاً إنجليزياً كملخص مترجَم) يستخدم الموديل الأساس المشترك، لأن
        # المقارنة بين متجهين من موديلين مختلفين غير صحيحة رياضياً (فضاءان مختلفان تماماً).
        scores_finetuned = cosine_similarity(finetuned_vectors, other_finetuned)
        scores_base = cosine_similarity(base_vectors, other_base)
        use_finetuned_mask = np.outer(own_is_ar, other_is_ar)
        scores = np.where(use_finetuned_mask, scores_finetuned, scores_base)

        best_index = np.unravel_index(np.argmax(scores), scores.shape)
        best_score = float(scores[best_index])
        if best_score >= suspected_threshold:
            # مطابقة واحدة معزولة بين عشرات مقاطع ورقتين كاملتين قد تحدث صدفة (مفردات أكاديمية
            # مشتركة بنفس التخصص) حتى لو كانت الورقتان غير مرتبطتين إطلاقاً — تأكَّد هذا تجريبياً
            # (دراسة rigor_gap_coverage_study.py). لذلك "التأكيد" يتطلب دليلاً داعماً من أكثر من
            # مقطع مستقل يطابق نفس الورقة الأخرى، لا أعلى قيمة واحدة فقط مهما علت — إلا إذا كانت
            # الورقة نفسها قصيرة جداً (أقل من الحد الأدنى من المقاطع) فلا معنى لطلب تعدد الأدلة.
            if len(finetuned_vectors) < min_corroborating_chunks:
                corroborating_chunks = 1 if best_score >= threshold else 0
                is_confirmed = best_score >= threshold
            else:
                row_best = scores.max(axis=1)
                corroborating_chunks = int((row_best >= corroboration_threshold).sum())
                is_confirmed = best_score >= threshold and corroborating_chunks >= min_corroborating_chunks

            # ترجيح عكسي بتكرار العبارة: مقطعنا الأفضل تطابقاً هنا قد يكون صياغة أكاديمية شائعة
            # عبر مكتبة كاملة (لا خاصة بهاتين الورقتين تحديداً) — إن كان كذلك، لا يُعتبَر دليلاً
            # كافياً للتأكيد مهما علت درجته مع هذه الورقة بالذات. تُستخدَم مكتبة الفضاء نفسه
            # (المُضبَط دقيقاً أو الأساس) الذي حسم أفضل تطابق تحديداً.
            if bool(use_finetuned_mask[best_index]):
                commonness_pool = (
                    np.concatenate([bootstrap_pool, live_finetuned_pool])
                    if len(bootstrap_pool) and len(live_finetuned_pool)
                    else (bootstrap_pool if len(bootstrap_pool) else live_finetuned_pool)
                )
                best_vector = finetuned_vectors[best_index[0]]
            else:
                commonness_pool = live_base_pool  # لا يوجد ملف مرجعي ثابت للموديل الأساس بعد
                best_vector = base_vectors[best_index[0]]
            commonness = _commonness_count(best_vector, commonness_pool, commonness_threshold)
            if commonness > commonness_max_count:
                is_confirmed = False

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
    chunks, finetuned_vectors, base_vectors, chunk_languages = store_chunk_embeddings(paper, raw_text)
    return find_internal_matches(paper, chunks, finetuned_vectors, base_vectors, chunk_languages)
