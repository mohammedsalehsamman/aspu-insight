from unittest.mock import MagicMock, patch

import numpy as np
from django.contrib.auth import get_user_model
from django.test import TestCase

from research.models import PaperEmbedding, ResearchPaper
from ai_service.services.research_recommendation import AIPaperSearchService

User = get_user_model()


def _make_paper(title, abstract="abstract text", specialization="informatics"):
    user = User.objects.create(email=f"{title}@example.com", full_name="Author", specialization=specialization)
    return ResearchPaper.objects.create(title=title, abstract=abstract, author=user, specialization=specialization)


class FakeModel:
    """Deterministic fake embedding model: returns the vector registered for each input string."""

    def __init__(self, vectors_by_text):
        self.vectors_by_text = vectors_by_text

    def encode(self, texts):
        return np.array([self.vectors_by_text[t] for t in texts])


class SemanticSearchTests(TestCase):
    def test_empty_query_returns_empty_list(self):
        self.assertEqual(AIPaperSearchService.semantic_search("", ResearchPaper.objects.all()), [])

    def test_no_papers_returns_empty_list(self):
        self.assertEqual(AIPaperSearchService.semantic_search("query", ResearchPaper.objects.none()), [])

    def test_ranks_and_filters_by_similarity_threshold(self):
        relevant = _make_paper("Relevant Paper")
        irrelevant = _make_paper("Irrelevant Paper")
        fake_model = FakeModel({
            "query text": [1.0, 0.0],
            "Relevant Paper abstract text informatics": [1.0, 0.0],
            "Irrelevant Paper abstract text informatics": [0.0, 1.0],
        })
        with patch("ai_service.utils.embeddings.get_embedding_model", return_value=fake_model):
            results = AIPaperSearchService.semantic_search(
                "query text", ResearchPaper.objects.all()
            )
        self.assertEqual(results, [relevant])

    def test_falls_back_to_plain_text_match_on_embedding_failure(self):
        _make_paper("Machine Learning Paper")
        _make_paper("Unrelated Topic Paper")
        with patch("ai_service.utils.embeddings.get_embedding_model", side_effect=RuntimeError("model unavailable")):
            results = AIPaperSearchService.semantic_search("machine learning", ResearchPaper.objects.all())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Machine Learning Paper")

    def test_uses_precomputed_embedding_when_available(self):
        paper = _make_paper("Paper With Stored Embedding")
        PaperEmbedding.objects.create(paper=paper, embedding_vector=[1.0, 0.0])
        fake_model = FakeModel({"query text": [1.0, 0.0]})
        with patch("ai_service.utils.embeddings.get_embedding_model", return_value=fake_model):
            results = AIPaperSearchService.semantic_search("query text", ResearchPaper.objects.all())
        self.assertEqual(results, [paper])


class RecommendSimilarPapersTests(TestCase):
    def test_excludes_self_from_candidates(self):
        paper = _make_paper("Target Paper")
        fake_model = FakeModel({
            "Target Paper abstract text informatics": [1.0, 0.0],
        })
        with patch("ai_service.utils.embeddings.get_embedding_model", return_value=fake_model):
            results = AIPaperSearchService.recommend_similar_papers(paper, ResearchPaper.objects.all())
        self.assertEqual(results, [])

    def test_ranks_candidates_by_similarity(self):
        target = _make_paper("Target Paper")
        similar = _make_paper("Similar Paper")
        different = _make_paper("Different Paper")
        fake_model = FakeModel({
            "Target Paper abstract text informatics": [1.0, 0.0],
            "Similar Paper abstract text informatics": [0.95, 0.05],
            "Different Paper abstract text informatics": [0.0, 1.0],
        })
        with patch("ai_service.utils.embeddings.get_embedding_model", return_value=fake_model):
            results = AIPaperSearchService.recommend_similar_papers(target, ResearchPaper.objects.all())
        self.assertEqual(results, [similar])

    def test_falls_back_to_same_specialization_on_embedding_failure(self):
        target = _make_paper("Target Paper", specialization="law")
        same_spec = _make_paper("Same Spec Paper", specialization="law")
        _make_paper("Other Spec Paper", specialization="medicine")
        with patch("ai_service.utils.embeddings.get_embedding_model", side_effect=RuntimeError("down")):
            results = AIPaperSearchService.recommend_similar_papers(target, ResearchPaper.objects.all())
        self.assertEqual(results, [same_spec])

    def test_no_candidates_returns_empty_list(self):
        paper = _make_paper("Lonely Paper")
        results = AIPaperSearchService.recommend_similar_papers(paper, ResearchPaper.objects.filter(id=paper.id))
        self.assertEqual(results, [])
