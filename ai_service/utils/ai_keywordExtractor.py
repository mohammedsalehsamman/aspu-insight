import os
from django.conf import settings
from keybert import KeyBERT

class AIKeywordExtractor:
    _instance = None
    _model = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(AIKeywordExtractor, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if AIKeywordExtractor._model is None:
            local_model_path = os.path.join(settings.BASE_DIR, 'my-model')
            AIKeywordExtractor._model = KeyBERT(model=local_model_path)

    def extract_pure_keywords(self, text: str, top_n=10) -> list:
        if not text or len(text.strip()) < 10:
            return []
        keywords_with_scores = AIKeywordExtractor._model.extract_keywords(
            text, 
            keyphrase_ngram_range=(1, 1), 
            stop_words='english', 
            top_n=top_n
        )
        pure_keywords = [item[0] for item in keywords_with_scores]
        return pure_keywords