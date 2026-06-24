"""
Lazy module-level singletons for Hugging Face / sentence-transformers models
used by the Claim-to-Evidence Graph feature.

Models are loaded on first use and cached at module scope, so within a
single worker process (Django dev server, gunicorn worker, or Celery
worker) each model is loaded exactly once and reused across
requests/tasks.
"""
from __future__ import annotations

import logging
import threading

from django.conf import settings

logger = logging.getLogger(__name__)

_embedding_model = None
_zero_shot_classifier = None
_lock = threading.Lock()


def get_embedding_model():
    """Return a cached SentenceTransformer instance for sentence embeddings.

    Loads `settings.CLAIM_EVIDENCE_EMBEDDING_MODEL`
    (default 'sentence-transformers/all-MiniLM-L6-v2') on first call.
    """
    global _embedding_model
    if _embedding_model is None:
        with _lock:
            if _embedding_model is None:
                from sentence_transformers import SentenceTransformer
                model_name = getattr(
                    settings, 'CLAIM_EVIDENCE_EMBEDDING_MODEL',
                    'sentence-transformers/all-MiniLM-L6-v2',
                )
                logger.info("Loading sentence embedding model: %s", model_name)
                _embedding_model = SentenceTransformer(model_name)
    return _embedding_model


def get_zero_shot_classifier():
    """Return a cached zero-shot-classification pipeline.

    Loads `settings.CLAIM_EVIDENCE_ZERO_SHOT_MODEL`
    (default 'valhalla/distilbart-mnli-12-3') on first call.
    """
    global _zero_shot_classifier
    if _zero_shot_classifier is None:
        with _lock:
            if _zero_shot_classifier is None:
                from transformers import pipeline
                model_name = getattr(
                    settings, 'CLAIM_EVIDENCE_ZERO_SHOT_MODEL',
                    'valhalla/distilbart-mnli-12-3',
                )
                logger.info("Loading zero-shot classification pipeline: %s", model_name)
                _zero_shot_classifier = pipeline(
                    "zero-shot-classification",
                    model=model_name,
                    device=-1,  # force CPU
                )
    return _zero_shot_classifier


def ensure_nltk_punkt() -> None:
    """Ensure the NLTK 'punkt'/'punkt_tab' tokenizer data is available, downloading if missing."""
    import nltk
    for resource in ('punkt', 'punkt_tab'):
        try:
            nltk.data.find(f'tokenizers/{resource}')
        except LookupError:
            logger.info("Downloading NLTK resource: %s", resource)
            nltk.download(resource, quiet=True)
