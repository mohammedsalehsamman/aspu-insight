from unittest.mock import patch

import torch
from django.test import SimpleTestCase, override_settings

from ai_service.ieee_checker.domain.entities import ReferenceEntry
from ai_service.ieee_checker.services.citation_semantic_matcher import find_citation_mismatches


class FakeEmbeddingModel:
    def __init__(self, vectors_by_text):
        self.vectors_by_text = vectors_by_text

    def encode(self, text, **kwargs):
        return torch.tensor(self.vectors_by_text[text])


@override_settings(IEEE_CHECKER_ENABLE_SEMANTIC_MATCH=True, IEEE_CHECKER_SEMANTIC_MISMATCH_THRESHOLD=0.15)
class FindCitationMismatchesTests(SimpleTestCase):
    def test_disabled_setting_returns_empty_list(self):
        with override_settings(IEEE_CHECKER_ENABLE_SEMANTIC_MATCH=False):
            result = find_citation_mismatches("text [1] more text.", [1], [])
        self.assertEqual(result, [])

    def test_no_citation_context_found_returns_empty_list(self):
        result = find_citation_mismatches("no bracket citations here at all", [1], [])
        self.assertEqual(result, [])

    def test_reference_without_title_skipped(self):
        ref = ReferenceEntry(index=1, raw_text="raw", title="")
        with patch(
            "ai_service.ieee_checker.services.citation_semantic_matcher.get_embedding_model",
            return_value=FakeEmbeddingModel({}),
        ):
            result = find_citation_mismatches("Some context around [1] citation here.", [1], [ref])
        self.assertEqual(result, [])

    def test_dissimilar_context_and_title_flagged_as_mismatch(self):
        context_text = "The distributed systems approach discussed in [1] handles this case well."
        ref = ReferenceEntry(index=1, raw_text="raw", title="A Paper About Marine Biology")
        fake_model = FakeEmbeddingModel({
            "The distributed systems approach discussed in [1] handles this case well": [1.0, 0.0],
            "A Paper About Marine Biology": [0.0, 1.0],
        })
        with patch(
            "ai_service.ieee_checker.services.citation_semantic_matcher.get_embedding_model",
            return_value=fake_model,
        ):
            result = find_citation_mismatches(context_text, [1], [ref])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["citation"], 1)

    def test_similar_context_and_title_not_flagged(self):
        context_text = "The marine biology methods discussed in [1] handles this case well."
        ref = ReferenceEntry(index=1, raw_text="raw", title="A Paper About Marine Biology")
        fake_model = FakeEmbeddingModel({
            "The marine biology methods discussed in [1] handles this case well": [1.0, 0.0],
            "A Paper About Marine Biology": [0.99, 0.02],
        })
        with patch(
            "ai_service.ieee_checker.services.citation_semantic_matcher.get_embedding_model",
            return_value=fake_model,
        ):
            result = find_citation_mismatches(context_text, [1], [ref])
        self.assertEqual(result, [])
