from keybert import KeyBERT

class AIKeywordExtractor:
    _instance = None
    _model = None

    def new(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(AIKeywordExtractor, cls).new(cls, *args, **kwargs)
        return cls._instance

    def init(self):
        if AIKeywordExtractor._model is None:
            AIKeywordExtractor._model = KeyBERT()

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