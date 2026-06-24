"""
Hybrid Claim/Evidence/Neutral sentence classifier combining rule-based
heuristics with a zero-shot NLI classification pipeline.
"""
from __future__ import annotations

import logging

from ..infrastructure.nlp_models import get_zero_shot_classifier
from .heuristics import score_sentence_heuristic

logger = logging.getLogger(__name__)

CANDIDATE_LABELS = ["claim", "evidence", "neutral"]

# Sentences shorter than this are classified as 'neutral' directly without
# invoking the zero-shot model (titles, headers, fragments).
MIN_SENTENCE_LENGTH = 15


def classify_sentence(sentence: str) -> dict:
    """Classify a single sentence as claim/evidence/neutral.

    Strategy:
        1. Run the cue-phrase heuristic to get a fast (label, boost) signal.
        2. If the sentence is too short, return 'neutral' immediately.
        3. Run the zero-shot classifier over `CANDIDATE_LABELS`.
        4. Add the heuristic boost to the zero-shot score for the
           matching label.
        5. Return the label with the highest combined score.

    Args:
        sentence: The sentence to classify.

    Returns:
        A dict `{"label": str, "score": float, "heuristic_label": str}`.
    """
    heuristic_label, boost = score_sentence_heuristic(sentence)

    if len(sentence.strip()) < MIN_SENTENCE_LENGTH:
        return {"label": "neutral", "score": 1.0, "heuristic_label": heuristic_label}

    try:
        classifier = get_zero_shot_classifier()
        result = classifier(sentence, candidate_labels=CANDIDATE_LABELS, multi_label=False)
        scores = dict(zip(result["labels"], result["scores"]))
    except Exception:
        logger.exception("Zero-shot classification failed for sentence; falling back to heuristic")
        if heuristic_label == "neutral":
            return {"label": "neutral", "score": 0.5, "heuristic_label": heuristic_label}
        return {"label": heuristic_label, "score": 0.5 + boost, "heuristic_label": heuristic_label}

    if heuristic_label != "neutral" and heuristic_label in scores:
        scores[heuristic_label] = min(1.0, scores[heuristic_label] + boost)

    final_label = max(scores, key=scores.get)
    return {"label": final_label, "score": scores[final_label], "heuristic_label": heuristic_label}


def classify_sentences(sentences: list[str]) -> list[dict]:
    """Classify a list of sentences.

    Args:
        sentences: The sentences to classify.

    Returns:
        A list of per-sentence results - see `classify_sentence` for shape.
    """
    return [classify_sentence(s) for s in sentences]
