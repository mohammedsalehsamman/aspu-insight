from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from ai_service.utils.ai_keywordExtractor import AIKeywordExtractor


class AIKeywordExtractorTests(SimpleTestCase):
    def setUp(self):
        AIKeywordExtractor._instance = None
        AIKeywordExtractor._model = None

    def tearDown(self):
        AIKeywordExtractor._instance = None
        AIKeywordExtractor._model = None

    def test_is_a_singleton(self):
        with patch("ai_service.utils.ai_keywordExtractor.KeyBERT"):
            first = AIKeywordExtractor()
            second = AIKeywordExtractor()
        self.assertIs(first, second)

    def test_short_text_returns_empty_list_without_calling_model(self):
        with patch("ai_service.utils.ai_keywordExtractor.KeyBERT") as mock_keybert_cls:
            extractor = AIKeywordExtractor()
            result = extractor.extract_pure_keywords("too short")
        self.assertEqual(result, [])
        mock_keybert_cls.return_value.extract_keywords.assert_not_called()

    def test_empty_text_returns_empty_list(self):
        with patch("ai_service.utils.ai_keywordExtractor.KeyBERT"):
            extractor = AIKeywordExtractor()
            self.assertEqual(extractor.extract_pure_keywords(""), [])
            self.assertEqual(extractor.extract_pure_keywords(None), [])

    def test_extracts_keyword_strings_from_scored_pairs(self):
        fake_model = MagicMock()
        fake_model.extract_keywords.return_value = [("machine learning", 0.6), ("neural networks", 0.4)]
        with patch("ai_service.utils.ai_keywordExtractor.KeyBERT", return_value=fake_model):
            extractor = AIKeywordExtractor()
            result = extractor.extract_pure_keywords("This is a long enough text about machine learning topics.", top_n=2)
        self.assertEqual(result, ["machine learning", "neural networks"])
        fake_model.extract_keywords.assert_called_once_with(
            "This is a long enough text about machine learning topics.",
            keyphrase_ngram_range=(1, 1), stop_words="english", top_n=2,
        )
