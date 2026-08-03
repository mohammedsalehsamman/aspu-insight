from unittest.mock import patch

import torch
from django.test import SimpleTestCase

from ai_service.claim_evidence.services.graph_builder import _segment_sentences, extract_graph


class FakeEmbeddingModel:
    """Deterministic fake: returns a hand-registered torch vector for each input sentence."""

    def __init__(self, vectors_by_sentence):
        self.vectors_by_sentence = vectors_by_sentence

    def encode(self, sentences, **kwargs):
        return torch.stack([torch.tensor(self.vectors_by_sentence[s]) for s in sentences])


def _fake_classify_sentences(results_by_sentence):
    def _classify(sentences, language="en"):
        return [results_by_sentence[s] for s in sentences]
    return _classify


class SegmentSentencesTests(SimpleTestCase):
    def test_splits_on_sentence_boundaries_without_real_nltk_punkt(self):
        # regression test for a real bug found while writing this test: _segment_sentences
        # used to call nltk.tokenize.sent_tokenize() unconditionally even when
        # ensure_nltk_punkt() reported punkt was unavailable, raising LookupError that
        # extract_graph's broad except silently swallowed into an always-empty result.
        # This environment genuinely has no cached punkt data, so this exercises the real
        # fallback path with no mocking needed.
        text = "This is the first sentence. This is the second sentence! Is this the third one?"
        sentences = _segment_sentences(text)
        self.assertEqual(len(sentences), 3)

    def test_filters_sentences_shorter_than_minimum(self):
        text = "Ok. This one is definitely long enough to be kept in the result."
        sentences = _segment_sentences(text)
        self.assertEqual(len(sentences), 1)


class ExtractGraphTests(SimpleTestCase):
    def test_empty_text_returns_empty_result(self):
        result = extract_graph("")
        self.assertEqual(result["nodes"], [])
        self.assertEqual(result["stats"]["claims"], 0)

    def test_builds_supports_edge_between_similar_claim_and_evidence(self):
        claim_sentence = "We propose that this new method improves detection accuracy significantly."
        evidence_sentence = "Results show a twenty five percent improvement in detection accuracy overall."
        neutral_sentence = "The paper was submitted to the conference in the month of March this year."

        fake_classify = _fake_classify_sentences({
            claim_sentence: {"label": "claim", "score": 0.8, "heuristic_label": "claim"},
            evidence_sentence: {"label": "evidence", "score": 0.8, "heuristic_label": "evidence"},
            neutral_sentence: {"label": "neutral", "score": 0.9, "heuristic_label": "neutral"},
        })
        fake_model = FakeEmbeddingModel({
            claim_sentence: [1.0, 0.0],
            evidence_sentence: [0.9, 0.1],
        })

        with patch(
            "ai_service.claim_evidence.services.graph_builder._segment_sentences",
            return_value=[claim_sentence, evidence_sentence, neutral_sentence],
        ), patch(
            "ai_service.claim_evidence.services.graph_builder.classify_sentences",
            side_effect=fake_classify,
        ), patch(
            "ai_service.claim_evidence.services.graph_builder.get_embedding_model",
            return_value=fake_model,
        ):
            result = extract_graph("irrelevant raw text")

        self.assertEqual(result["stats"], {"claims": 1, "evidence": 1, "neutral": 1, "edges": 1})
        self.assertEqual(len(result["edges"]), 1)
        edge = result["edges"][0]
        self.assertEqual(edge["label"], "supports")
        self.assertEqual(len(result["top_claims"]), 1)
        self.assertEqual(result["top_claims"][0]["supporting_evidence_count"], 1)

    def test_no_edge_when_claim_and_evidence_are_dissimilar(self):
        claim_sentence = "We propose an entirely new theoretical approach to this specific problem."
        evidence_sentence = "Results show no measurable change whatsoever in the unrelated control group."

        fake_classify = _fake_classify_sentences({
            claim_sentence: {"label": "claim", "score": 0.8, "heuristic_label": "claim"},
            evidence_sentence: {"label": "evidence", "score": 0.8, "heuristic_label": "evidence"},
        })
        fake_model = FakeEmbeddingModel({
            claim_sentence: [1.0, 0.0],
            evidence_sentence: [0.0, 1.0],
        })

        with patch(
            "ai_service.claim_evidence.services.graph_builder._segment_sentences",
            return_value=[claim_sentence, evidence_sentence],
        ), patch(
            "ai_service.claim_evidence.services.graph_builder.classify_sentences",
            side_effect=fake_classify,
        ), patch(
            "ai_service.claim_evidence.services.graph_builder.get_embedding_model",
            return_value=fake_model,
        ):
            result = extract_graph("irrelevant raw text")

        self.assertEqual(result["edges"], [])

    def test_exception_during_extraction_returns_empty_result_with_error(self):
        with patch(
            "ai_service.claim_evidence.services.graph_builder._segment_sentences",
            side_effect=RuntimeError("boom"),
        ):
            result = extract_graph("some text")
        self.assertEqual(result["nodes"], [])
        self.assertIn("error", result)
