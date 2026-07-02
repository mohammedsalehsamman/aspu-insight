import os
from django.conf import settings
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

class AIReviewerMatcherService:
    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            # استخدام المسار الفعلي الدقيق المكتوب بالشرطة العادية
            model_path = r"C:\Users\hp\Desktop\aspuinsight\aspu-insight\my-model"
            
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Could not find model directory at: {model_path}")
                
            cls._model = SentenceTransformer(model_path, local_files_only=True)
        return cls._model

    @classmethod
    def rank_reviewers_by_specialization(cls, paper_specialization, reviewers_queryset):
        paper_spec = (paper_specialization or "").strip().lower()
        
        if not paper_spec or not reviewers_queryset.exists():
            return []

        reviewers_list = [
            r for r in reviewers_queryset 
            if r.specialization and r.specialization.strip()
        ]
        
        if not reviewers_list:
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