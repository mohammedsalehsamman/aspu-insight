"""
Rule-based cue-phrase heuristics for classifying scientific-paper sentences
as Claim, Evidence, or Neutral.

These heuristics are intentionally lightweight (string matching + a couple
of regexes) and act as a fast pre-signal that is combined with the
zero-shot model in `classifier.classify_sentence`. English only - the
zero-shot model and embedding model used elsewhere in this package are
English-centric, so Arabic sentences will typically fall back to "neutral".
"""
from __future__ import annotations

import re

CLAIM_CUES = [
    "we propose", "we argue", "we claim", "we hypothesize", "we believe",
    "this suggests", "this indicates", "this implies", "we contend",
    "our approach", "we present", "we introduce", "this paper proposes",
    "we assume", "it is likely that", "we expect", "should be considered",
    "we recommend", "this demonstrates the need", "in our view",
]

EVIDENCE_CUES = [
    "results show", "results indicate", "as shown in table", "as shown in figure",
    "figure", "table", "as illustrated in", "the data show", "experiments show",
    "we observed", "we found that", "according to the results",
    "the experiment demonstrates", "as depicted in", "p <", "p-value",
    "statistically significant", "% of", "percent", "increase of", "decrease of",
    "compared to", "outperform", "accuracy of", "correlation",
]

_NUMERIC_RE = re.compile(r'\b\d+(\.\d+)?\s*(%|percent)\b', re.IGNORECASE)
_TABLE_FIGURE_RE = re.compile(r'\b(table|figure|fig\.)\s*\d+\b', re.IGNORECASE)


def score_sentence_heuristic(sentence: str) -> tuple[str, float]:
    """Return (label, confidence_boost) based on cue-phrase / numeric heuristics.

    Args:
        sentence: The sentence to score.

    Returns:
        A tuple `(label, confidence_boost)` where `label` is one of
        "claim", "evidence", "neutral", and `confidence_boost` is in
        [0.0, 0.3] - the amount to add to the zero-shot score for the
        matching label (see `classifier.classify_sentence`).
    """
    text_lower = sentence.lower()

    evidence_score = sum(1 for cue in EVIDENCE_CUES if cue in text_lower)
    claim_score = sum(1 for cue in CLAIM_CUES if cue in text_lower)

    if _TABLE_FIGURE_RE.search(sentence):
        evidence_score += 2
    if _NUMERIC_RE.search(sentence):
        evidence_score += 1

    if evidence_score == 0 and claim_score == 0:
        return "neutral", 0.0

    if evidence_score > claim_score:
        return "evidence", min(0.3, 0.1 * evidence_score)
    if claim_score > evidence_score:
        return "claim", min(0.3, 0.1 * claim_score)

    return "neutral", 0.0
