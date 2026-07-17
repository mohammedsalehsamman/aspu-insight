"""
AI-based IEEE format compliance judgment for a single reference entry.

Hybrid approach (same pattern as ``claim_evidence/services/heuristics.py`` +
``classifier.py``): the fast rule-based checks in ``format_validator.py``
run first to catch obviously missing fields instantly, then the local LLM
is asked to judge the reference holistically against IEEE citation style
rules and explain any subtler issues in natural Arabic. Falls back to the
rule-based result alone if the model is unavailable or its output cannot
be parsed.
"""
from __future__ import annotations

import json
import logging
import re
from typing import List

from ..domain.entities import ReferenceEntry
from ..infrastructure.nlp_models import get_extraction_llm
from .format_validator import validate_ieee_format

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r'\{.*\}', re.DOTALL)

_VALIDATION_PROMPT = """You are an expert reviewer checking academic references against IEEE \
citation style. IEEE style: "F. Lastname, \\"Title,\\" Source, vol. X, no. Y, pp. Z-W, Year."

Reference fields extracted:
authors: {authors}
title: {title}
source: {source}
year: {year}
doi: {doi}
pages: {pages}

Judge whether this reference is IEEE-compliant. Return ONLY a JSON object, no explanation, \
no markdown fences, in this exact shape:
{{"compliant": true or false, "errors": ["short Arabic description of each problem found"], "confidence": 0.0 to 1.0}}

If there are no problems, return an empty errors list.

JSON:"""


def validate_ieee_format_ai(ref: ReferenceEntry) -> List[str]:
    """Return a list of Arabic format-error strings for ``ref``.

    Combines the fast rule-based checks with an LLM judgment call; falls
    back to rule-based-only output if the model fails.
    """
    rule_errors = validate_ieee_format(ref)

    try:
        model, tokenizer = get_extraction_llm()
        import torch

        prompt_text = _VALIDATION_PROMPT.format(
            authors=ref.authors or "(missing)",
            title=ref.title or "(missing)",
            source=ref.source or "(missing)",
            year=ref.year or "(missing)",
            doi=ref.doi or "(missing)",
            pages=ref.pages or "(missing)",
        )
        messages = [{"role": "user", "content": prompt_text}]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt")

        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=200,
                do_sample=False,
                temperature=None,
                top_p=None,
                pad_token_id=tokenizer.eos_token_id,
            )

        generated = output_ids[0][inputs["input_ids"].shape[1]:]
        text = tokenizer.decode(generated, skip_special_tokens=True)

        match = _JSON_BLOCK_RE.search(text)
        if not match:
            raise ValueError(f"No JSON object found in LLM output: {text[:200]!r}")

        parsed = json.loads(match.group(0))
        ai_errors = [str(err).strip() for err in parsed.get("errors", []) if str(err).strip()]

        merged = list(dict.fromkeys(rule_errors + ai_errors))
        return merged

    except Exception as e:
        logger.warning("AI format validation failed, using rule-based result only: %s", e)
        return rule_errors
