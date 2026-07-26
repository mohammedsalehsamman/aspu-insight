from __future__ import annotations

import logging
import re
from typing import Dict, List, Tuple

from django.conf import settings

from ..infrastructure.nlp_models import get_zero_shot_classifier

logger = logging.getLogger(__name__)

_SECTION_LABELS = [
    "Abstract",
    "Introduction",
    "Related Work",
    "Methodology",
    "Results",
    "Discussion",
    "Conclusion",
    "Acknowledgment",
    "References",
]

_REQUIRED_SECTIONS = ["Abstract", "Introduction", "Conclusion", "References"]

_EXPECTED_ORDER = [
    "Abstract", "Introduction", "Related Work", "Methodology",
    "Results", "Discussion", "Conclusion", "Acknowledgment", "References",
]

_HEADING_RE = re.compile(
    r'^\s*(?:[IVXLCDM]+\.|[0-9]+\.?)?\s*'
    r'([A-Z][A-Za-z ]{2,40}|[A-Z][A-Z ]{2,40})\s*$'
)

_LABEL_SYNONYMS: Dict[str, List[str]] = {
    "Abstract": ["abstract"],
    "Introduction": ["introduction", "background"],
    "Related Work": ["related work", "related works", "literature review", "prior work"],
    "Methodology": ["methodology", "methods", "materials and methods", "proposed method", "proposed approach", "system model"],
    "Results": ["results", "experimental results", "evaluation", "experiments"],
    "Discussion": ["discussion", "results and discussion"],
    "Conclusion": ["conclusion", "conclusions", "conclusion and future work", "summary"],
    "Acknowledgment": ["acknowledgment", "acknowledgement", "acknowledgments", "acknowledgements"],
    "References": ["references", "bibliography", "works cited"],
}

_NUMBERING_RE = re.compile(r'^\s*(?:[IVXLCDM]+\.|[0-9]+\.?)\s*')

_MIN_CONFIDENCE = 0.35

def _find_heading_candidates(full_text: str) -> List[str]:
    candidates = []
    for line in full_text.splitlines():
        line = line.strip()
        if not line or len(line) > 45 or len(line) < 3:
            continue
        if _HEADING_RE.match(line):
            candidates.append(line)

    seen = set()
    unique = []
    for c in candidates:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique[:60]

def _match_synonym(heading: str) -> str | None:
    normalized = _NUMBERING_RE.sub('', heading).strip().lower()
    for label, synonyms in _LABEL_SYNONYMS.items():
        if normalized in synonyms:
            return label
    return None

def check_paper_structure(full_text: str) -> Dict[str, object]:
    if not getattr(settings, "IEEE_CHECKER_ENABLE_SECTION_CHECK", True):
        return {
            "detected_sections": [],
            "missing_required_sections": [],
            "section_order_valid": True,
            "structure_score": 0.0,
        }

    candidates = _find_heading_candidates(full_text)
    detected: List[str] = []
    unmatched: List[str] = []

    for heading in candidates:
        label = _match_synonym(heading)
        if label and label not in detected:
            detected.append(label)
        elif not label:
            unmatched.append(heading)

    if unmatched:
        try:
            classifier = get_zero_shot_classifier()
            for heading in unmatched:
                result = classifier(heading, _SECTION_LABELS, multi_label=False)
                top_label = result["labels"][0]
                top_score = result["scores"][0]
                if top_score >= _MIN_CONFIDENCE and top_label not in detected:
                    detected.append(top_label)
        except Exception as e:
            logger.warning("Section structure zero-shot classification failed: %s", e)

    missing_required = [s for s in _REQUIRED_SECTIONS if s not in detected]

    order_valid = _is_order_valid(detected)

    total_expected = len(_REQUIRED_SECTIONS)
    present_required = total_expected - len(missing_required)
    base_score = (present_required / total_expected) * 100.0 if total_expected else 0.0
    if not order_valid:
        base_score = max(0.0, base_score - 15.0)

    return {
        "detected_sections": detected,
        "missing_required_sections": missing_required,
        "section_order_valid": order_valid,
        "structure_score": round(base_score, 1),
    }

def _is_order_valid(detected: List[str]) -> bool:
    positions = [_EXPECTED_ORDER.index(s) for s in detected if s in _EXPECTED_ORDER]
    return positions == sorted(positions)
