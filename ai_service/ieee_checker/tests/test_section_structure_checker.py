from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from ai_service.ieee_checker.services.section_structure_checker import check_paper_structure


@override_settings(IEEE_CHECKER_ENABLE_SECTION_CHECK=True)
class CheckPaperStructureTests(SimpleTestCase):
    def test_disabled_setting_returns_inert_result(self):
        with override_settings(IEEE_CHECKER_ENABLE_SECTION_CHECK=False):
            result = check_paper_structure("Abstract\nIntroduction\nConclusion\nReferences\n")
        self.assertEqual(result["detected_sections"], [])
        self.assertEqual(result["structure_score"], 0.0)

    def test_all_required_sections_present_in_order(self):
        text = "Abstract\nsome text\nIntroduction\nsome text\nConclusion\nsome text\nReferences\nsome text\n"
        with patch(
            "ai_service.ieee_checker.services.section_structure_checker.get_zero_shot_classifier"
        ) as mock_clf:
            result = check_paper_structure(text)
        mock_clf.assert_not_called()
        self.assertEqual(result["missing_required_sections"], [])
        self.assertTrue(result["section_order_valid"])
        self.assertEqual(result["structure_score"], 100.0)

    def test_missing_required_section_detected(self):
        text = "Abstract\nsome text\nIntroduction\nsome text\nReferences\nsome text\n"
        result = check_paper_structure(text)
        self.assertEqual(result["missing_required_sections"], ["Conclusion"])
        self.assertEqual(result["structure_score"], 75.0)

    def test_out_of_order_sections_penalized(self):
        text = "Introduction\nsome text\nAbstract\nsome text\nConclusion\nsome text\nReferences\nsome text\n"
        result = check_paper_structure(text)
        self.assertFalse(result["section_order_valid"])
        self.assertEqual(result["structure_score"], 85.0)

    def test_synonym_heading_recognized(self):
        text = "Abstract\nsome text\nBackground\nsome text\nConclusions\nsome text\nBibliography\nsome text\n"
        result = check_paper_structure(text)
        self.assertIn("Introduction", result["detected_sections"])
        self.assertIn("Conclusion", result["detected_sections"])
        self.assertIn("References", result["detected_sections"])

    def test_unmatched_heading_falls_back_to_zero_shot_classifier(self):
        text = "Abstract\nsome text\nIntroduction\nsome text\nAn Unusual Heading Title\nsome text\nConclusion\nsome text\nReferences\nsome text\n"
        mock_classifier = lambda heading, labels, multi_label=False: {
            "labels": ["Methodology", "Results"], "scores": [0.9, 0.05],
        }
        with patch(
            "ai_service.ieee_checker.services.section_structure_checker.get_zero_shot_classifier",
            return_value=mock_classifier,
        ):
            result = check_paper_structure(text)
        self.assertIn("Methodology", result["detected_sections"])

    def test_zero_shot_failure_does_not_crash(self):
        text = "Abstract\nsome text\nIntroduction\nsome text\nAn Unusual Heading Title\nsome text\nConclusion\nsome text\nReferences\nsome text\n"
        with patch(
            "ai_service.ieee_checker.services.section_structure_checker.get_zero_shot_classifier",
            side_effect=RuntimeError("model unavailable"),
        ):
            result = check_paper_structure(text)
        self.assertEqual(result["missing_required_sections"], [])
