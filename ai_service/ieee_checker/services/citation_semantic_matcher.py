from __future__ import annotations

import logging
import re
from typing import Dict, List

from django.conf import settings

from ..domain.entities import ReferenceEntry
from ..infrastructure.nlp_models import get_embedding_model

logger = logging.getLogger(__name__)

_MAX_CITATIONS_CHECKED = 40

def _extract_citation_contexts(full_text: str, citation_numbers: List[int]) -> Dict[int, str]:
    contexts: Dict[int, str] = {}
    for n in citation_numbers[:_MAX_CITATIONS_CHECKED]:
        pattern = re.compile(rf'([^.]{{0,150}}\[{n}\][^.]{{0,150}})')
        m = pattern.search(full_text)
        if m:
            contexts[n] = re.sub(r'\s+', ' ', m.group(1)).strip()
    return contexts

def find_citation_mismatches(
    full_text: str,
    citation_numbers: List[int],
    references: List[ReferenceEntry],
) -> List[Dict[str, object]]:
    if not getattr(settings, "IEEE_CHECKER_ENABLE_SEMANTIC_MATCH", True):
        return []

    ref_by_index = {ref.index: ref for ref in references}
    contexts = _extract_citation_contexts(full_text, citation_numbers)
    if not contexts:
        return []

    threshold = getattr(settings, "IEEE_CHECKER_SEMANTIC_MISMATCH_THRESHOLD", 0.15)

    try:
        from sentence_transformers import util as st_util

        model = get_embedding_model()
        mismatches: List[Dict[str, object]] = []

        for n, context in contexts.items():
            ref = ref_by_index.get(n)
            if not ref or not ref.title:
                continue

            context_emb = model.encode(context, convert_to_tensor=True)
            title_emb = model.encode(ref.title, convert_to_tensor=True)
            similarity = float(st_util.cos_sim(context_emb, title_emb)[0][0])

            if similarity < threshold:
                mismatches.append({
                    "citation": n,
                    "reference_title": ref.title,
                    "similarity": round(similarity, 3),
                })

        return mismatches

    except Exception as e:
        logger.warning("Citation semantic matching failed, skipping: %s", e)
        return []
