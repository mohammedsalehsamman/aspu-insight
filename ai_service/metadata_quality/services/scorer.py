from __future__ import annotations

import logging
import re

from django.core.exceptions import ObjectDoesNotExist

from ..constants import (
    ABSTRACT_COMPONENT_LABELS,
    ABSTRACT_COMPONENT_THRESHOLD,
    ABSTRACT_IDEAL_MAX_WORDS,
    ABSTRACT_IDEAL_MIN_WORDS,
    ABSTRACT_MAX_WORDS,
    ABSTRACT_MIN_WORDS,
    DIMENSION_LABELS_AR,
    DIMENSION_WEIGHTS,
    KEYWORD_RELEVANCE_MIN_SIMILARITY,
    KEYWORDS_IDEAL_MAX,
    KEYWORDS_IDEAL_MIN,
    NEUTRAL_FALLBACK_SCORE,
    ORCID_PATTERN,
    TITLE_ABSTRACT_MIN_SIMILARITY,
    TITLE_MAX_LEN,
    TITLE_MIN_LEN,
)

logger = logging.getLogger(__name__)

_SENTENCE_BOUNDARY_RE = re.compile(r'(?<=[.!?؟])\s+')
_TITLE_PLACEHOLDER_TERMS = {"untitled", "test", "بدون عنوان", "عنوان تجريبي", "n/a", "تجربة"}
_COMPONENT_LABELS_AR = {
    "objective": "الهدف",
    "methodology": "المنهجية",
    "results": "النتائج",
    "conclusion": "الاستنتاج",
}


def _segment_sentences(text: str) -> list[str]:
    try:
        from ai_service.utils.nltk_setup import ensure_nltk_punkt
        ensure_nltk_punkt()
        from nltk.tokenize import sent_tokenize
        raw_chunks = sent_tokenize(text)
    except Exception:
        raw_chunks = [text]

    sentences: list[str] = []
    for chunk in raw_chunks:
        sentences.extend(_SENTENCE_BOUNDARY_RE.split(chunk))
    return [s.strip() for s in sentences if len(s.strip()) >= 10]


def _extract_paper_text(paper) -> str:
    if not paper.pdf_file:
        return ""
    try:
        from ai_service.ieee_checker.infrastructure.file_parser import extract_text_from_file
        text, _pages, _file_type = extract_text_from_file(paper.pdf_file.path)
        return text or ""
    except Exception:
        logger.exception("Could not extract PDF text for paper %s", paper.id)
        return ""


def _get_keywords(paper) -> list[str]:
    try:
        report = paper.plagiarism_report
        if report.ai_keywords:
            return report.ai_keywords
    except ObjectDoesNotExist:
        pass
    except Exception:
        logger.exception("Could not read existing ai_keywords for paper %s", paper.id)

    text = _extract_paper_text(paper) or paper.abstract or ""
    if not text.strip():
        return []
    try:
        from ai_service.utils.ai_keywordExtractor import AIKeywordExtractor
        return AIKeywordExtractor().extract_pure_keywords(text, top_n=8)
    except Exception:
        logger.exception("Keyword extraction failed for paper %s", paper.id)
        return []


# ---------------------------------------------------------------------------
# أبعاد لا تحتاج ذكاءً اصطناعياً — قراءة/تحقق مباشر من حقول قاعدة البيانات
# ---------------------------------------------------------------------------

def _score_title(title: str | None) -> tuple[float, str]:
    if not title or not title.strip():
        return 0.0, "العنوان مفقود"

    title = title.strip()
    if title.lower() in _TITLE_PLACEHOLDER_TERMS:
        return 10.0, "العنوان يبدو نصاً افتراضياً/تجريبياً"

    length = len(title)
    if TITLE_MIN_LEN <= length <= TITLE_MAX_LEN:
        return 100.0, "طول العنوان مناسب"
    if length < TITLE_MIN_LEN:
        return max(0.0, (length / TITLE_MIN_LEN) * 60), "العنوان قصير جداً"
    over_chars = length - TITLE_MAX_LEN
    return max(0.0, 100.0 - over_chars * 0.5), "العنوان طويل جداً"


def _score_abstract_basic(abstract: str | None) -> tuple[float, str]:
    if not abstract or not abstract.strip():
        return 0.0, "الملخص مفقود"

    word_count = len(abstract.split())
    if ABSTRACT_IDEAL_MIN_WORDS <= word_count <= ABSTRACT_IDEAL_MAX_WORDS:
        return 100.0, f"طول الملخص مناسب ({word_count} كلمة)"
    if word_count < ABSTRACT_MIN_WORDS:
        return max(0.0, (word_count / ABSTRACT_MIN_WORDS) * 40), f"الملخص قصير جداً ({word_count} كلمة)"
    if word_count < ABSTRACT_IDEAL_MIN_WORDS:
        ratio = (word_count - ABSTRACT_MIN_WORDS) / (ABSTRACT_IDEAL_MIN_WORDS - ABSTRACT_MIN_WORDS)
        return 40.0 + ratio * 60.0, f"الملخص أقصر من المعتاد ({word_count} كلمة)"
    if word_count > ABSTRACT_MAX_WORDS:
        return max(0.0, 40.0 - (word_count - ABSTRACT_MAX_WORDS) * 0.1), f"الملخص طويل جداً ({word_count} كلمة)"
    ratio = (ABSTRACT_MAX_WORDS - word_count) / (ABSTRACT_MAX_WORDS - ABSTRACT_IDEAL_MAX_WORDS)
    return 40.0 + ratio * 60.0, f"الملخص أطول من المعتاد ({word_count} كلمة)"


def _score_keywords_presence(keywords: list[str]) -> tuple[float, str]:
    count = len(keywords or [])
    if count == 0:
        return 0.0, "لا توجد كلمات مفتاحية"
    if KEYWORDS_IDEAL_MIN <= count <= KEYWORDS_IDEAL_MAX:
        return 100.0, f"عدد الكلمات المفتاحية مناسب ({count})"
    if count < KEYWORDS_IDEAL_MIN:
        return (count / KEYWORDS_IDEAL_MIN) * 70.0, f"عدد الكلمات المفتاحية قليل ({count})"
    over = count - KEYWORDS_IDEAL_MAX
    return max(30.0, 100.0 - over * 10), f"عدد الكلمات المفتاحية أكثر من اللازم ({count})"


def _score_specialization(specialization: str | None) -> tuple[float, str]:
    if specialization and specialization.strip():
        return 100.0, "التخصص/المجال العلمي محدد"
    return 0.0, "التخصص/المجال العلمي غير محدد"


def _score_author_info(author) -> tuple[float, str]:
    if author is None:
        return 0.0, "لا يوجد مؤلف مرتبط بالبحث"

    score = 0.0
    notes = []

    institution = getattr(author, 'institution', '') or ''
    if institution.strip():
        score += 50.0
    else:
        notes.append("المؤسسة/الانتماء غير محدد")

    orcid = getattr(author, 'orcid_id', '') or ''
    if orcid.strip() and re.match(ORCID_PATTERN, orcid.strip()):
        score += 50.0
    elif orcid.strip():
        notes.append("معرّف ORCID موجود لكن بصيغة غير صحيحة")
    else:
        notes.append("معرّف ORCID غير محدد")

    message = "بيانات المؤلف مكتملة" if score == 100.0 else "؛ ".join(notes)
    return score, message


def _score_completeness(paper) -> tuple[float, str]:
    if not paper.pdf_file:
        return 0.0, "لا يوجد ملف PDF مرفوع للبحث"
    return 100.0, "ملف البحث مرفوع بصيغة صحيحة"

def _score_abstract_structure(abstract: str | None) -> tuple[float, str]:
    if not abstract or not abstract.strip():
        return 0.0, "لا يمكن تحليل بنية الملخص لأنه مفقود"

    if len(abstract.split()) < ABSTRACT_MIN_WORDS:
        return 0.0, "الملخص قصير جداً لتحليل بنيته العلمية"

    sentences = _segment_sentences(abstract) or [abstract.strip()]

    try:
        from ai_service.claim_evidence.infrastructure.nlp_models import get_zero_shot_classifier

        classifier = get_zero_shot_classifier()
        candidate_labels = list(ABSTRACT_COMPONENT_LABELS.values())
        results = classifier(sentences, candidate_labels=candidate_labels, multi_label=True)
        if isinstance(results, dict):
            results = [results]

        detected_labels = set()
        for result in results:
            for label, score in zip(result["labels"], result["scores"]):
                if score >= ABSTRACT_COMPONENT_THRESHOLD:
                    detected_labels.add(label)

        detected_keys = [key for key, label in ABSTRACT_COMPONENT_LABELS.items() if label in detected_labels]
        score = (len(detected_keys) / len(ABSTRACT_COMPONENT_LABELS)) * 100

        missing_keys = [key for key in ABSTRACT_COMPONENT_LABELS if key not in detected_keys]
        if missing_keys:
            missing_ar = "، ".join(_COMPONENT_LABELS_AR[key] for key in missing_keys)
            message = f"مكوّنات ناقصة في الملخص: {missing_ar}"
        else:
            message = "الملخص يغطي جميع المكوّنات العلمية الأساسية (الهدف، المنهجية، النتائج، الاستنتاج)"

        return score, message
    except Exception:
        logger.exception("Abstract structure scoring (zero-shot) failed; using neutral fallback")
        return NEUTRAL_FALLBACK_SCORE, "تعذّر تحليل بنية الملخص دلالياً"


def _score_keywords_relevance(keywords: list[str], abstract: str | None) -> tuple[float, str]:
    if not keywords:
        return 0.0, "لا توجد كلمات مفتاحية لقياس صلتها بالملخص"
    if not abstract or not abstract.strip():
        return NEUTRAL_FALLBACK_SCORE, "لا يمكن قياس الصلة لعدم وجود ملخص"

    try:
        from sklearn.metrics.pairwise import cosine_similarity

        from ai_service.utils.embeddings import get_embedding_model

        model = get_embedding_model()
        abstract_vector = model.encode([abstract])
        keyword_vectors = model.encode(list(keywords))
        similarities = cosine_similarity(keyword_vectors, abstract_vector).flatten()

        relevant_count = int((similarities >= KEYWORD_RELEVANCE_MIN_SIMILARITY).sum())
        score = min(100.0, (relevant_count / len(keywords)) * 100)
        message = f"{relevant_count} من {len(keywords)} كلمة مفتاحية ذات صلة واضحة بالملخص"
        return score, message
    except Exception:
        logger.exception("Keyword relevance scoring failed; using neutral fallback")
        return NEUTRAL_FALLBACK_SCORE, "تعذّر تحليل صلة الكلمات المفتاحية دلالياً"


def _score_title_abstract_coherence(title: str | None, abstract: str | None) -> tuple[float, str]:
    if not title or not abstract or not title.strip() or not abstract.strip():
        return 0.0, "العنوان أو الملخص مفقود"

    try:
        from sklearn.metrics.pairwise import cosine_similarity

        from ai_service.utils.embeddings import get_embedding_model

        model = get_embedding_model()
        vectors = model.encode([title, abstract])
        similarity = float(cosine_similarity([vectors[0]], [vectors[1]])[0][0])

        if similarity >= TITLE_ABSTRACT_MIN_SIMILARITY:
            score = min(100.0, 60 + (similarity - TITLE_ABSTRACT_MIN_SIMILARITY) * 200)
            message = "العنوان يعكس محتوى الملخص بشكل جيد"
        else:
            score = max(0.0, (similarity / TITLE_ABSTRACT_MIN_SIMILARITY) * 60)
            message = "العنوان قد لا يعكس محتوى الملخص بدقة"

        return score, message
    except Exception:
        logger.exception("Title-abstract coherence scoring failed; using neutral fallback")
        return NEUTRAL_FALLBACK_SCORE, "تعذّر تحليل الاتساق الدلالي بين العنوان والملخص"


def _score_language_consistency(paper) -> tuple[float, str]:
    text = _extract_paper_text(paper) or (paper.abstract or "")
    if not text.strip():
        return NEUTRAL_FALLBACK_SCORE, "تعذّر فحص اللغة لعدم توفر نص كافٍ"

    try:
        from ai_service.ieee_checker.services.citation_extractor import detect_language

        language = detect_language(text)
        if language in ("ar", "en"):
            return 100.0, f"اللغة واضحة ومتسقة ({language})"
        if language == "mixed":
            return 50.0, "النص يحتوي خلطاً ملحوظاً بين لغتين"
        return 20.0, "تعذّر تحديد لغة النص بوضوح"
    except Exception:
        logger.exception("Language consistency check failed for paper %s", paper.id)
        return NEUTRAL_FALLBACK_SCORE, "تعذّر فحص اتساق اللغة"


def _build_recommendations(breakdown: list[dict]) -> list[str]:
    return [
        f"{item['label']}: {item['message']}"
        for item in breakdown
        if item["score"] < 70
    ]


def compute_metadata_quality(paper) -> dict:
    breakdown: list[dict] = []
    sub_scores: dict[str, float] = {}

    def add(dimension: str, score: float, message: str) -> None:
        weight = DIMENSION_WEIGHTS[dimension]
        clamped_score = max(0.0, min(100.0, score))
        sub_scores[dimension] = round(clamped_score, 1)
        breakdown.append({
            "dimension": dimension,
            "label": DIMENSION_LABELS_AR[dimension],
            "score": round(clamped_score, 1),
            "weight": weight,
            "weighted_contribution": round(clamped_score * weight / 100, 2),
            "message": message,
        })

    add("title", *_score_title(paper.title))
    add("abstract_basic", *_score_abstract_basic(paper.abstract))
    add("abstract_structure", *_score_abstract_structure(paper.abstract))

    keywords = _get_keywords(paper)
    add("keywords_presence", *_score_keywords_presence(keywords))
    add("keywords_relevance", *_score_keywords_relevance(keywords, paper.abstract))

    add("title_abstract_coherence", *_score_title_abstract_coherence(paper.title, paper.abstract))
    add("specialization", *_score_specialization(paper.specialization))
    add("language_consistency", *_score_language_consistency(paper))
    add("author_info", *_score_author_info(paper.author))
    add("completeness", *_score_completeness(paper))

    overall_score = round(sum(item["weighted_contribution"] for item in breakdown), 1)

    return {
        "overall_score": overall_score,
        "sub_scores": sub_scores,
        "breakdown": breakdown,
        "recommendations": _build_recommendations(breakdown),
    }
