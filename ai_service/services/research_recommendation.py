from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

class AIPaperSearchService:

    @staticmethod
    def rank_papers_by_search_query(search_query, papers_queryset):
        query_text = (search_query or "").strip().lower()
        if not query_text or not papers_queryset.exists():
            return list(papers_queryset)

        papers_list = list(papers_queryset)
        corpus = [query_text]

        for paper in papers_list:
            title = (paper.title or "").strip().lower()
            abstract = (paper.abstract or "").strip().lower()
            keywords = (paper.keywords or "").strip().lower()
            
            combined_text = f"{title} {abstract} {keywords}"
            corpus.append(combined_text)

        vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        tfidf_matrix = vectorizer.fit_transform(corpus)

        similarity_scores = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()

        scored_papers = []
        for index, score in enumerate(similarity_scores):
            if score >= 0.05:
                scored_papers.append({
                    'paper_obj': papers_list[index],
                    'score': score
                })

        scored_papers.sort(key=lambda x: x['score'], reverse=True)

        return [item['paper_obj'] for item in scored_papers]