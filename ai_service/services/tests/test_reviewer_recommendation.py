from unittest.mock import patch

import numpy as np
from django.contrib.auth import get_user_model
from django.test import TestCase

from ai_service.services.reviewer_recommendation import AIReviewerMatcherService

User = get_user_model()


class FakeModel:
    def __init__(self, vectors_by_text):
        self.vectors_by_text = vectors_by_text

    def encode(self, texts):
        return np.array([self.vectors_by_text[t] for t in texts])


def _make_reviewer(email, specialization):
    return User.objects.create(email=email, full_name="Reviewer", role="reviewer", specialization=specialization)


class RankReviewersBySpecializationTests(TestCase):
    def test_empty_specialization_returns_empty_list(self):
        _make_reviewer("r1@example.com", "law")
        results = AIReviewerMatcherService.rank_reviewers_by_specialization("", User.objects.all())
        self.assertEqual(results, [])

    def test_no_reviewers_returns_empty_list(self):
        results = AIReviewerMatcherService.rank_reviewers_by_specialization("law", User.objects.none())
        self.assertEqual(results, [])

    def test_skips_reviewers_without_specialization(self):
        no_spec = User.objects.create(email="nospec@example.com", full_name="No Spec", role="reviewer", specialization="")
        matching = _make_reviewer("match@example.com", "law")
        fake_model = FakeModel({"law": [1.0, 0.0]})
        with patch("ai_service.services.reviewer_recommendation.get_embedding_model", return_value=fake_model):
            results = AIReviewerMatcherService.rank_reviewers_by_specialization("law", User.objects.all())
        self.assertEqual(results, [matching])

    def test_filters_below_threshold_and_sorts_descending(self):
        strong_match = _make_reviewer("strong@example.com", "law")
        weak_match = _make_reviewer("weak@example.com", "accounting")
        below_threshold = _make_reviewer("below@example.com", "medicine")
        fake_model = FakeModel({
            "law": [1.0, 0.0],
            "accounting": [0.9, 0.1],
            "medicine": [0.0, 1.0],
        })
        with patch("ai_service.services.reviewer_recommendation.get_embedding_model", return_value=fake_model):
            results = AIReviewerMatcherService.rank_reviewers_by_specialization("law", User.objects.all())
        self.assertEqual(results, [strong_match, weak_match])
        self.assertNotIn(below_threshold, results)
