from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from ai_service.ieee_checker.domain.entities import ReferenceEntry
from ai_service.ieee_checker.services.format_validator_ai import validate_ieee_format_ai


def _valid_ref(**overrides):
    defaults = dict(
        index=1, raw_text="raw", authors="F. Lastname",
        title="A Great Paper Title", source="IEEE Transactions", year="2021",
        pages="12-20",
    )
    defaults.update(overrides)
    return ReferenceEntry(**defaults)


class ValidateIeeeFormatAiTests(SimpleTestCase):
    def test_llm_unavailable_falls_back_to_rule_based_errors_only(self):
        ref = _valid_ref(authors="")
        with patch(
            "ai_service.ieee_checker.services.format_validator_ai.get_extraction_llm",
            side_effect=RuntimeError("model unavailable"),
        ):
            errors = validate_ieee_format_ai(ref)
        self.assertTrue(any("المؤلف" in e for e in errors))

    def test_llm_adds_extra_error_merged_with_rule_based(self):
        ref = _valid_ref()
        fake_tokenizer = MagicMock()
        fake_tokenizer.apply_chat_template.return_value = "prompt"
        fake_tokenizer.return_value = {"input_ids": MagicMock(shape=(1, 5))}
        fake_tokenizer.decode.return_value = '{"compliant": false, "errors": ["مشكلة إضافية من الذكاء الاصطناعي"], "confidence": 0.8}'
        fake_model = MagicMock()
        fake_model.generate.return_value = [list(range(10))]

        with patch(
            "ai_service.ieee_checker.services.format_validator_ai.get_extraction_llm",
            return_value=(fake_model, fake_tokenizer),
        ), patch("torch.no_grad"):
            errors = validate_ieee_format_ai(ref)

        self.assertIn("مشكلة إضافية من الذكاء الاصطناعي", errors)

    def test_llm_output_without_json_falls_back_to_rule_based(self):
        ref = _valid_ref(year="")
        fake_tokenizer = MagicMock()
        fake_tokenizer.apply_chat_template.return_value = "prompt"
        fake_tokenizer.return_value = {"input_ids": MagicMock(shape=(1, 5))}
        fake_tokenizer.decode.return_value = "no json here at all"
        fake_model = MagicMock()
        fake_model.generate.return_value = [list(range(10))]

        with patch(
            "ai_service.ieee_checker.services.format_validator_ai.get_extraction_llm",
            return_value=(fake_model, fake_tokenizer),
        ), patch("torch.no_grad"):
            errors = validate_ieee_format_ai(ref)

        self.assertTrue(any("سنة النشر" in e for e in errors))
