import os
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

class AIReviewerMatcherService:
    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            
            cls._model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        return cls._model

    @classmethod
    def rank_reviewers_by_specialization(cls, paper_specialization, reviewers_queryset):
       
        print(f"--- [DEBUG] Total input reviewers count: {reviewers_queryset.count()} ---")
        
        
        reviewers_list = [r for r in reviewers_queryset if r.specialization and r.specialization.strip()]
        print(f"--- [DEBUG] Reviewers with valid specialization: {len(reviewers_list)} ---")
        
        paper_spec = (paper_specialization or "").strip().lower()
        print(f"--- [DEBUG] Paper specialization input: '{paper_spec}' ---")
        
        if not paper_spec or not reviewers_list:
            print("--- [DEBUG] RETURNING EMPTY LIST because input is missing or no reviewers found ---")
            return []

        
        model = cls.get_model()
        paper_embedding = model.encode([paper_spec])
        reviewer_specs = [r.specialization.strip().lower() for r in reviewers_list]
        reviewer_embeddings = model.encode(reviewer_specs)
        
        similarity_scores = cosine_similarity(paper_embedding, reviewer_embeddings).flatten()

        scored_reviewers = []
        for index, score in enumerate(similarity_scores):
            
            if score >= 0.25: 
                scored_reviewers.append({
                    'user_obj': reviewers_list[index],
                    'score': score
                })

        scored_reviewers.sort(key=lambda x: x['score'], reverse=True)
        return [item['user_obj'] for item in scored_reviewers]