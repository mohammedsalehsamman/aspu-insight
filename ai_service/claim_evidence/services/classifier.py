"""
Hybrid Claim/Evidence/Neutral sentence classifier combining rule-based
heuristics with a zero-shot NLI classification pipeline.

Language handling: English (and "mixed"/"unknown") sentences are
classified via the heuristic + zero-shot combination described below.
Arabic sentences are classified from the cue-phrase heuristic alone (see
`heuristics.py`), skipping the zero-shot model entirely - empirical
testing found the multilingual zero-shot model strongly and confidently
biased toward "evidence" for Arabic input (misclassifying clear Arabic
claim sentences, and even unrelated neutral sentences, as evidence with
90%+ confidence), regardless of the NLI hypothesis template or label
wording tried. The heuristic cue lists, by contrast, correctly classified
every tested Arabic claim/evidence sentence, so trusting them directly
for Arabic avoids injecting that model bias into the results.
"""
from __future__ import annotations

import logging

from ..infrastructure.nlp_models import get_zero_shot_classifier
from .heuristics import score_sentence_heuristic

logger = logging.getLogger(__name__)

CANDIDATE_LABELS = ["claim", "evidence", "neutral"]
HYPOTHESIS_TEMPLATE = "This example is {}."

# Sentences shorter than this are classified as 'neutral' directly without
# invoking the zero-shot model (titles, headers, fragments).
MIN_SENTENCE_LENGTH = 15

# Batch size for the zero-shot pipeline call - bounds peak memory while still
# processing far fewer Python-level calls than one-per-sentence.
ZERO_SHOT_BATCH_SIZE = 16


def _heuristic_only_result(heuristic_label: str, boost: float) -> dict:
    if heuristic_label == "neutral":
        return {"label": "neutral", "score": 0.5, "heuristic_label": heuristic_label}
    return {"label": heuristic_label, "score": min(1.0, 0.5 + boost), "heuristic_label": heuristic_label}


def classify_sentences(sentences: list[str], language: str = "en") -> list[dict]:
    """Classify a list of sentences as claim/evidence/neutral.

    Strategy:
        1. Run the cue-phrase heuristic on every sentence to get a fast
           (label, boost) signal.
        2. Sentences too short to be meaningful are classified as
           'neutral' immediately, without invoking the zero-shot model.
        3. Arabic sentences (`language == "ar"`) are classified from the
           heuristic alone (see module docstring for why).
        4. Remaining (English/mixed/unknown) sentences are classified in a
           single batched call to the zero-shot pipeline; the heuristic
           boost is added to the zero-shot score for the matching label,
           and the label with the highest combined score is returned.

    Args:
        sentences: The sentences to classify.
        language: The document's detected language ("ar", "en", "mixed",
            or "unknown"). Only "ar" changes behavior (heuristic-only).

    Returns:
        A list of dicts `{"label": str, "score": float, "heuristic_label": str}`,
        one per input sentence, in the same order.
    """
    heuristics = [score_sentence_heuristic(s) for s in sentences]

    results: list[dict | None] = [None] * len(sentences)
    to_classify_indices: list[int] = []
    to_classify_sentences: list[str] = []

    for i, (sentence, (heuristic_label, boost)) in enumerate(zip(sentences, heuristics)):
        if len(sentence.strip()) < MIN_SENTENCE_LENGTH:
            results[i] = {"label": "neutral", "score": 1.0, "heuristic_label": heuristic_label}
        elif language == "ar":
            results[i] = _heuristic_only_result(heuristic_label, boost)
        else:
            to_classify_indices.append(i)
            to_classify_sentences.append(sentence)

    if to_classify_sentences:
        try:
            classifier = get_zero_shot_classifier()
            batch_results = classifier(
                to_classify_sentences,
                candidate_labels=CANDIDATE_LABELS,
                hypothesis_template=HYPOTHESIS_TEMPLATE,
                multi_label=False,
                batch_size=ZERO_SHOT_BATCH_SIZE,
            )
            if isinstance(batch_results, dict):
                batch_results = [batch_results]
        except Exception:
            logger.exception(
                "Zero-shot classification failed for a batch of %d sentence(s); "
                "falling back to heuristic labels for the whole batch",
                len(to_classify_sentences),
            )
            for idx in to_classify_indices:
                results[idx] = _heuristic_only_result(*heuristics[idx])
        else:
            for idx, result in zip(to_classify_indices, batch_results):
                heuristic_label, boost = heuristics[idx]
                scores = dict(zip(result["labels"], result["scores"]))
                if heuristic_label != "neutral" and heuristic_label in scores:
                    scores[heuristic_label] = min(1.0, scores[heuristic_label] + boost)
                final_label = max(scores, key=scores.get)
                results[idx] = {"label": final_label, "score": scores[final_label], "heuristic_label": heuristic_label}

    return results


def classify_sentence(sentence: str, language: str = "en") -> dict:
    """Classify a single sentence as claim/evidence/neutral.

    Thin wrapper around `classify_sentences` for isolated/manual use; see
    that function for the classification strategy.

    Args:
        sentence: The sentence to classify.
        language: The document's detected language - see `classify_sentences`.

    Returns:
        A dict `{"label": str, "score": float, "heuristic_label": str}`.
    """
    return classify_sentences([sentence], language)[0]
