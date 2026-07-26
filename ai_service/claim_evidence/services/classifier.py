from __future__ import annotations

import logging

from ..infrastructure.nlp_models import get_zero_shot_classifier
from .heuristics import score_sentence_heuristic

logger = logging.getLogger(__name__)

CANDIDATE_LABELS = ["claim", "evidence", "neutral"]
HYPOTHESIS_TEMPLATE = "This example is {}."

MIN_SENTENCE_LENGTH = 15

ZERO_SHOT_BATCH_SIZE = 16

def _heuristic_only_result(heuristic_label: str, boost: float) -> dict:
    if heuristic_label == "neutral":
        return {"label": "neutral", "score": 0.5, "heuristic_label": heuristic_label}
    return {"label": heuristic_label, "score": min(1.0, 0.5 + boost), "heuristic_label": heuristic_label}

def classify_sentences(sentences: list[str], language: str = "en") -> list[dict]:
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
    return classify_sentences([sentence], language)[0]
