from sklearn.metrics.pairwise import cosine_similarity

from ai_service.utils.embeddings import get_embedding_model

class AIReviewerMatcherService:

    @classmethod
    def rank_reviewers_by_specialization(cls, paper_specialization, reviewers_queryset):
        reviewers_list = [r for r in reviewers_queryset if r.specialization and r.specialization.strip()]
        paper_spec = (paper_specialization or "").strip().lower()

        if not paper_spec or not reviewers_list:
            return []

        model = get_embedding_model()
        paper_embedding = model.encode([paper_spec])
        reviewer_specs = [r.specialization.strip().lower() for r in reviewers_list]
        reviewer_embeddings = model.encode(reviewer_specs)

        similarity_scores = cosine_similarity(paper_embedding, reviewer_embeddings).flatten()

        scored_reviewers = [
            {'user_obj': reviewers_list[index], 'score': score}
            for index, score in enumerate(similarity_scores)
            if score >= 0.25
        ]
        scored_reviewers.sort(key=lambda x: x['score'], reverse=True)

        return [item['user_obj'] for item in scored_reviewers]
