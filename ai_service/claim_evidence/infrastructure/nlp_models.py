from __future__ import annotations

import logging
import threading

from django.conf import settings

from ai_service.utils.embeddings import get_embedding_model as _get_shared_embedding_model

logger = logging.getLogger(__name__)

_zero_shot_classifier = None
_lock = threading.Lock()

def get_embedding_model():
    model_name = getattr(
        settings, 'CLAIM_EVIDENCE_EMBEDDING_MODEL',
        'sentence-transformers/all-MiniLM-L6-v2',
    )
    return _get_shared_embedding_model(model_name)

def get_zero_shot_classifier():
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
                    device=-1,
                )
    return _zero_shot_classifier
