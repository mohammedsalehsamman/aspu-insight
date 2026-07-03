import os
from django.conf import settings
from sentence_transformers import SentenceTransformer

class PlagiarismAnalyzer:
    def __init__(self):
        local_model_path = os.path.join(settings.BASE_DIR, 'my-model')
        self.model = SentenceTransformer(local_model_path)
        self.chunk_size = 30

    def calculate_similarity(self, text, paper_id):
        if not text:
            return {'total_score': 0.0, 'ai_tags': [], 'sources': []}
        
        chunks = [text[i:i + self.chunk_size * 100] for i in range(0, len(text), self.chunk_size * 100)]
        embeddings = self.model.encode(chunks)
        
        total_score = 0
        if len(embeddings) > 0:
            total_score = float(sum([abs(e[0]) for e in embeddings]) / len(embeddings)) * 100
        
        return {
            'total_score': min(total_score, 100.0),
            'ai_tags': [],
            'sources': []
        }