from unittest.mock import patch

from django.test import SimpleTestCase

from ai_service.claim_evidence.services.classifier import classify_sentence, classify_sentences


class ClassifySentencesTests(SimpleTestCase):
    def test_short_sentence_is_neutral_without_calling_classifier(self):
        with patch("ai_service.claim_evidence.services.classifier.get_zero_shot_classifier") as mock_get_clf:
            results = classify_sentences(["Too short."], language="en")
        mock_get_clf.assert_not_called()
        self.assertEqual(results[0]["label"], "neutral")
        self.assertEqual(results[0]["score"], 1.0)

    def test_arabic_language_uses_heuristic_only_without_calling_classifier(self):
        sentence = "أظهرت النتائج تحسناً واضحاً وملحوظاً في أداء النموذج المقترح للتصنيف."
        with patch("ai_service.claim_evidence.services.classifier.get_zero_shot_classifier") as mock_get_clf:
            results = classify_sentences([sentence], language="ar")
        mock_get_clf.assert_not_called()
        self.assertEqual(results[0]["label"], "evidence")

    def test_english_long_sentence_uses_zero_shot_classifier(self):
        sentence = "The building was originally constructed sometime during the year nineteen ninety by workers."
        mock_classifier = lambda sentences, **kwargs: [
            {"labels": ["neutral", "claim", "evidence"], "scores": [0.6, 0.3, 0.1]}
            for _ in sentences
        ]
        with patch(
            "ai_service.claim_evidence.services.classifier.get_zero_shot_classifier",
            return_value=mock_classifier,
        ):
            results = classify_sentences([sentence], language="en")
        self.assertEqual(results[0]["label"], "neutral")
        self.assertAlmostEqual(results[0]["score"], 0.6)

    def test_heuristic_boost_can_flip_zero_shot_decision(self):
        # zero-shot slightly favors "neutral" (0.4) over "claim" (0.35), but a strong
        # heuristic claim boost (+0.3, capped) should push "claim" over the top.
        sentence = "We propose we argue we claim we hypothesize a new approach for this problem entirely."
        mock_classifier = lambda sentences, **kwargs: [
            {"labels": ["neutral", "claim", "evidence"], "scores": [0.4, 0.35, 0.25]}
            for _ in sentences
        ]
        with patch(
            "ai_service.claim_evidence.services.classifier.get_zero_shot_classifier",
            return_value=mock_classifier,
        ):
            results = classify_sentences([sentence], language="en")
        self.assertEqual(results[0]["label"], "claim")

    def test_zero_shot_failure_falls_back_to_heuristic(self):
        sentence = "We propose a completely new theoretical framework for this specific research problem."
        with patch(
            "ai_service.claim_evidence.services.classifier.get_zero_shot_classifier",
            side_effect=RuntimeError("model load failed"),
        ):
            results = classify_sentences([sentence], language="en")
        self.assertEqual(results[0]["label"], "claim")
        self.assertEqual(results[0]["heuristic_label"], "claim")

    def test_classify_sentence_singular_wrapper(self):
        with patch("ai_service.claim_evidence.services.classifier.get_zero_shot_classifier") as mock_get_clf:
            result = classify_sentence("Too short.", language="en")
        mock_get_clf.assert_not_called()
        self.assertEqual(result["label"], "neutral")
