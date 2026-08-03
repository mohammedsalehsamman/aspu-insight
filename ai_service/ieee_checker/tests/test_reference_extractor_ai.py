from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from ai_service.ieee_checker.services.reference_extractor_ai import (
    _ner_cross_check,
    extract_reference_fields,
)


class NerCrossCheckTests(SimpleTestCase):
    def test_empty_authors_returns_zero_confidence(self):
        self.assertEqual(_ner_cross_check("some text", ""), 0.0)

    def test_ner_failure_returns_medium_confidence(self):
        with patch(
            "ai_service.ieee_checker.services.reference_extractor_ai.get_ner_pipeline",
            side_effect=RuntimeError("model unavailable"),
        ):
            confidence = _ner_cross_check("some text", "F. Lastname")
        self.assertEqual(confidence, 0.5)

    def test_no_person_entities_found_returns_low_confidence(self):
        fake_ner = MagicMock(return_value=[{"word": "Paris", "entity_group": "LOC"}])
        with patch(
            "ai_service.ieee_checker.services.reference_extractor_ai.get_ner_pipeline",
            return_value=fake_ner,
        ):
            confidence = _ner_cross_check("some text", "F. Lastname")
        self.assertEqual(confidence, 0.3)

    def test_matching_person_entity_gives_full_confidence(self):
        fake_ner = MagicMock(return_value=[{"word": "Lastname", "entity_group": "PER"}])
        with patch(
            "ai_service.ieee_checker.services.reference_extractor_ai.get_ner_pipeline",
            return_value=fake_ner,
        ):
            confidence = _ner_cross_check("some text", "F. Lastname")
        self.assertEqual(confidence, 1.0)


class ExtractReferenceFieldsTests(SimpleTestCase):
    def test_llm_unavailable_falls_back_to_regex_parser(self):
        ref_text = 'F. Lastname, "A Great Paper Title," IEEE Transactions, 2021.'
        with patch(
            "ai_service.ieee_checker.services.reference_extractor_ai.get_extraction_llm",
            side_effect=RuntimeError("model unavailable"),
        ):
            result = extract_reference_fields(ref_text)
        self.assertEqual(result["extraction_method"], "regex_fallback")
        self.assertEqual(result["extraction_confidence"], 0.0)
        self.assertEqual(result["title"], "A Great Paper Title,")

    def test_llm_returning_no_usable_fields_falls_back_to_regex(self):
        ref_text = 'F. Lastname, "A Great Paper Title," IEEE Transactions, 2021.'
        fake_tokenizer = MagicMock()
        fake_tokenizer.apply_chat_template.return_value = "prompt"
        fake_tokenizer.return_value = {"input_ids": MagicMock(shape=(1, 5))}
        fake_tokenizer.decode.return_value = '{"authors": "", "title": "", "source": "", "year": "", "doi": "", "url": "", "volume": "", "issue": "", "pages": ""}'
        fake_model = MagicMock()
        fake_model.generate.return_value = [list(range(10))]

        with patch(
            "ai_service.ieee_checker.services.reference_extractor_ai.get_extraction_llm",
            return_value=(fake_model, fake_tokenizer),
        ), patch("torch.no_grad"):
            result = extract_reference_fields(ref_text)
        self.assertEqual(result["extraction_method"], "regex_fallback")

    def test_successful_llm_extraction_used_with_ner_confidence(self):
        ref_text = 'F. Lastname, "A Great Paper Title," IEEE Transactions, 2021.'
        fake_tokenizer = MagicMock()
        fake_tokenizer.apply_chat_template.return_value = "prompt"
        fake_tokenizer.return_value = {"input_ids": MagicMock(shape=(1, 5))}
        fake_tokenizer.decode.return_value = (
            '{"authors": "F. Lastname", "title": "A Great Paper Title", "source": "IEEE Transactions", '
            '"year": "2021", "doi": "", "url": "", "volume": "", "issue": "", "pages": ""}'
        )
        fake_model = MagicMock()
        fake_model.generate.return_value = [list(range(10))]
        fake_ner = MagicMock(return_value=[{"word": "Lastname", "entity_group": "PER"}])

        with patch(
            "ai_service.ieee_checker.services.reference_extractor_ai.get_extraction_llm",
            return_value=(fake_model, fake_tokenizer),
        ), patch(
            "ai_service.ieee_checker.services.reference_extractor_ai.get_ner_pipeline",
            return_value=fake_ner,
        ), patch("torch.no_grad"):
            result = extract_reference_fields(ref_text)

        self.assertEqual(result["extraction_method"], "ai")
        self.assertEqual(result["authors"], "F. Lastname")
        self.assertEqual(result["extraction_confidence"], 1.0)
