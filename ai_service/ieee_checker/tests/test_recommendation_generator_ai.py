from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from ai_service.ieee_checker.domain.entities import IEEECheckResult
from ai_service.ieee_checker.services.recommendation_generator_ai import (
    _parse_llm_output,
    generate_recommendations_and_summary_ai,
)


class ParseLlmOutputTests(SimpleTestCase):
    def test_parses_summary_and_bullet_recommendations(self):
        text = "ملخص: هذا ملخص قصير للورقة.\nتوصيات:\n- أضف المزيد من المراجع.\n- صحح تنسيق الاستشهادات.\n"
        summary, recs = _parse_llm_output(text)
        self.assertEqual(summary, "هذا ملخص قصير للورقة.")
        self.assertEqual(recs, ["أضف المزيد من المراجع.", "صحح تنسيق الاستشهادات."])

    def test_missing_summary_line_returns_empty_summary(self):
        text = "- أضف المزيد من المراجع.\n"
        summary, recs = _parse_llm_output(text)
        self.assertEqual(summary, "")
        self.assertEqual(recs, ["أضف المزيد من المراجع."])

    def test_no_bullet_lines_returns_empty_recommendations(self):
        text = "ملخص: هذا ملخص فقط بدون توصيات.\n"
        summary, recs = _parse_llm_output(text)
        self.assertEqual(summary, "هذا ملخص فقط بدون توصيات.")
        self.assertEqual(recs, [])


class GenerateRecommendationsAndSummaryAiTests(SimpleTestCase):
    def test_llm_unavailable_falls_back_to_template(self):
        result = IEEECheckResult(paper_title="Test Paper", overall_score=90.0, status="pass")
        with patch(
            "ai_service.ieee_checker.services.recommendation_generator_ai.get_extraction_llm",
            side_effect=RuntimeError("model unavailable"),
        ):
            summary, recs = generate_recommendations_and_summary_ai(result)
        self.assertIn("Test Paper", summary)
        self.assertTrue(len(recs) >= 1)

    def test_incomplete_llm_output_falls_back_to_template(self):
        result = IEEECheckResult(paper_title="Test Paper", overall_score=90.0, status="pass")
        fake_tokenizer = MagicMock()
        fake_tokenizer.apply_chat_template.return_value = "prompt"
        fake_tokenizer.return_value = {"input_ids": MagicMock(shape=(1, 5))}
        fake_tokenizer.decode.return_value = "ملخص: \n"
        fake_model = MagicMock()
        fake_model.generate.return_value = [list(range(10))]

        with patch(
            "ai_service.ieee_checker.services.recommendation_generator_ai.get_extraction_llm",
            return_value=(fake_model, fake_tokenizer),
        ), patch("torch.no_grad"):
            summary, recs = generate_recommendations_and_summary_ai(result)
        self.assertIn("Test Paper", summary)

    def test_complete_llm_output_used_directly(self):
        result = IEEECheckResult(paper_title="Test Paper", overall_score=90.0, status="pass")
        fake_tokenizer = MagicMock()
        fake_tokenizer.apply_chat_template.return_value = "prompt"
        fake_tokenizer.return_value = {"input_ids": MagicMock(shape=(1, 5))}
        fake_tokenizer.decode.return_value = "ملخص: ملخص مولَّد بالذكاء الاصطناعي.\nتوصيات:\n- توصية أولى.\n"
        fake_model = MagicMock()
        fake_model.generate.return_value = [list(range(10))]

        with patch(
            "ai_service.ieee_checker.services.recommendation_generator_ai.get_extraction_llm",
            return_value=(fake_model, fake_tokenizer),
        ), patch("torch.no_grad"):
            summary, recs = generate_recommendations_and_summary_ai(result)
        self.assertEqual(summary, "ملخص مولَّد بالذكاء الاصطناعي.")
        self.assertEqual(recs, ["توصية أولى."])
