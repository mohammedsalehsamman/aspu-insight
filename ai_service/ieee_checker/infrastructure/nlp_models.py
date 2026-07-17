"""
Lazy module-level singletons for the AI models used by the IEEE checker.

Follows the same pattern as ``claim_evidence/infrastructure/nlp_models.py``:
each model is loaded on first use and cached at module scope, so within a
single worker process (Django dev server, gunicorn worker, or Celery
worker) it is loaded exactly once and reused across requests/tasks.

The zero-shot classifier and the sentence embedding model are NOT
re-declared here — they are the exact same models already loaded by the
``claim_evidence`` feature, so we import and reuse those singletons
directly to avoid holding two copies of the same weights in memory.
"""
from __future__ import annotations

import logging
import threading

from django.conf import settings

from ai_service.claim_evidence.infrastructure.nlp_models import (
    get_embedding_model,
    get_zero_shot_classifier,
)

logger = logging.getLogger(__name__)

__all__ = [
    "get_embedding_model",
    "get_zero_shot_classifier",
    "get_extraction_llm",
    "get_ner_pipeline",
]

_llm_model = None
_llm_tokenizer = None
_ner_pipeline = None
_lock = threading.Lock()


def get_extraction_llm():
    """Return a cached (model, tokenizer) pair for the reference-extraction LLM.

    Loads `settings.IEEE_CHECKER_LLM_MODEL` (default
    'Qwen/Qwen2.5-1.5B-Instruct') on first call.
    """
    global _llm_model, _llm_tokenizer
    if _llm_model is None or _llm_tokenizer is None:
        with _lock:
            if _llm_model is None or _llm_tokenizer is None:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer

                model_name = getattr(
                    settings, "IEEE_CHECKER_LLM_MODEL", "Qwen/Qwen2.5-1.5B-Instruct"
                )
                logger.info("Loading IEEE checker extraction LLM: %s", model_name)
                _llm_tokenizer = AutoTokenizer.from_pretrained(model_name)
                _llm_model = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    torch_dtype=torch.float32,
                    device_map=None,
                )
                _llm_model.eval()
    return _llm_model, _llm_tokenizer


def get_ner_pipeline():
    """Return a cached NER pipeline used as an auxiliary cross-check on author names.

    Loads `settings.IEEE_CHECKER_NER_MODEL` (default 'dslim/bert-base-NER')
    on first call.
    """
    global _ner_pipeline
    if _ner_pipeline is None:
        with _lock:
            if _ner_pipeline is None:
                from transformers import pipeline

                model_name = getattr(
                    settings, "IEEE_CHECKER_NER_MODEL", "dslim/bert-base-NER"
                )
                logger.info("Loading IEEE checker NER pipeline: %s", model_name)
                _ner_pipeline = pipeline(
                    "ner",
                    model=model_name,
                    aggregation_strategy="simple",
                    device=-1,  # force CPU
                )
    return _ner_pipeline
