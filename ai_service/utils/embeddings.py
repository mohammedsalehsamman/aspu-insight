from functools import lru_cache
from django.conf import settings


@lru_cache(maxsize=None)
def get_embedding_model(model_name=None):
    from sentence_transformers import SentenceTransformer
    resolved_name = model_name or getattr(
        settings,
        'CLAIM_EVIDENCE_EMBEDDING_MODEL',
        'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
    )
    return SentenceTransformer(resolved_name)
