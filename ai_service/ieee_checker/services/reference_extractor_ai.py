"""
AI-based structured extraction of reference fields from a raw reference string.

Uses the local instruction-tuned LLM (see ``infrastructure/nlp_models.py``)
to understand a reference string written in any citation style and pull out
its fields as JSON, instead of relying on a fixed cascade of regexes that
only matches IEEE-shaped text exactly. Falls back to the original
regex-based ``parse_ieee_reference`` whenever the model is unavailable, its
output cannot be parsed as JSON, or an unexpected error occurs — the
feature must never break just because the model failed once.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict

from django.conf import settings

from ..infrastructure.nlp_models import get_extraction_llm, get_ner_pipeline
from .reference_parser import parse_ieee_reference

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r'\{.*\}', re.DOTALL)

_FIELDS = ('authors', 'title', 'source', 'year', 'doi', 'url', 'volume', 'issue', 'pages')

_EXTRACTION_PROMPT = """You are a bibliographic reference parser. Extract the fields from the \
following academic reference string and return ONLY a single JSON object, no explanation, \
no markdown fences. Use empty string "" for any field you cannot find.

Fields: authors, title, source (journal/conference/publisher), year, doi, url, volume, issue, pages.

Reference string:
\"\"\"{ref_text}\"\"\"

JSON:"""


def _empty_result() -> Dict[str, str]:
    return {f: "" for f in _FIELDS}


def _run_llm_extraction(ref_text: str) -> Dict[str, str]:
    model, tokenizer = get_extraction_llm()
    import torch

    messages = [{"role": "user", "content": _EXTRACTION_PROMPT.format(ref_text=ref_text[:800])}]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt")

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=256,
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
    result = _empty_result()
    for field_name in _FIELDS:
        value = parsed.get(field_name, "")
        if isinstance(value, list):
            value = ", ".join(str(v).strip() for v in value if str(v).strip())
        result[field_name] = str(value).strip() if value else ""
    return result


def _ner_cross_check(ref_text: str, extracted_authors: str) -> float:
    """Return a rough confidence (0-1) that the extracted authors match NER PER entities."""
    if not extracted_authors:
        return 0.0
    try:
        ner = get_ner_pipeline()
        entities = ner(ref_text[:400])
    except Exception as e:
        logger.warning("IEEE checker NER cross-check failed: %s", e)
        return 0.5  # neutral confidence when NER itself is unavailable

    person_entities = [e['word'] for e in entities if e.get('entity_group') == 'PER']
    if not person_entities:
        return 0.3

    authors_lower = extracted_authors.lower()
    matches = sum(1 for name in person_entities if any(part.lower() in authors_lower for part in name.split()))
    return min(1.0, matches / max(1, len(person_entities)))


def extract_reference_fields(ref_text: str) -> Dict[str, object]:
    """Extract structured fields from a raw reference string using the local LLM.

    Returns a dict with the same keys as ``parse_ieee_reference`` plus
    ``extraction_method`` ("ai" or "regex_fallback") and
    ``extraction_confidence`` (float 0-1).
    """
    try:
        fields = _run_llm_extraction(ref_text)
        if not fields['authors'] and not fields['title']:
            raise ValueError("LLM extraction returned no usable fields")

        confidence = _ner_cross_check(ref_text, fields['authors'])
        fields['extraction_method'] = "ai"
        fields['extraction_confidence'] = round(confidence, 2)
        return fields
    except Exception as e:
        logger.warning("AI reference extraction failed, falling back to regex: %s", e)
        fallback = parse_ieee_reference(ref_text)
        fallback['extraction_method'] = "regex_fallback"
        fallback['extraction_confidence'] = 0.0
        return fallback
