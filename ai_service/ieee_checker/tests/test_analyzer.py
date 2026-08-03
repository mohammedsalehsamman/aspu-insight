from unittest.mock import patch

from django.test import SimpleTestCase

from ai_service.ieee_checker.services.analyzer import perform_ieee_analysis

_ANALYZER = "ai_service.ieee_checker.services.analyzer"


class PerformIeeeAnalysisTests(SimpleTestCase):
    def test_unextractable_file_returns_fail_status_without_further_processing(self):
        with patch(f"{_ANALYZER}.extract_text_from_file", return_value=("", 0, "unknown")):
            result = perform_ieee_analysis("/tmp/scanned.pdf")
        self.assertEqual(result["status"], "fail")
        self.assertIn("تعذّر استخراج النص", result["summary"])

    def test_full_pipeline_orchestrates_all_stages(self):
        full_text = 'A Paper About Something Important\nAbstract\n...\nSee [1] for details.\nReferences\n[1] F. Lastname, "A Cited Paper," Journal, 2020.\n'

        parsed_ref = {
            "authors": "F. Lastname", "title": "A Cited Paper", "source": "Journal",
            "year": "2020", "doi": "10.1109/EXAMPLE.2020.1", "url": "", "volume": "", "issue": "", "pages": "",
            "extraction_method": "ai", "extraction_confidence": 0.9,
        }

        with patch(f"{_ANALYZER}.extract_text_from_file", return_value=(full_text, 5, "pdf")), \
             patch(f"{_ANALYZER}.find_references_section", return_value="References\n[1] ...\n"), \
             patch(f"{_ANALYZER}.split_references_section", return_value=[(1, 'F. Lastname, "A Cited Paper," Journal, 2020.')]), \
             patch(f"{_ANALYZER}.extract_reference_fields", return_value=parsed_ref), \
             patch(f"{_ANALYZER}.validate_ieee_format_ai", return_value=[]), \
             patch(f"{_ANALYZER}.verify_doi", return_value=(True, "تم التحقق")), \
             patch(f"{_ANALYZER}.check_paper_structure", return_value={
                 "detected_sections": ["Abstract", "Introduction", "Conclusion", "References"],
                 "missing_required_sections": [], "section_order_valid": True, "structure_score": 100.0,
             }), \
             patch(f"{_ANALYZER}.find_citation_mismatches", return_value=[]), \
             patch(f"{_ANALYZER}.generate_recommendations_and_summary_ai", return_value=("summary text", ["rec 1"])), \
             patch(f"{_ANALYZER}.time.sleep"):
            result = perform_ieee_analysis("/tmp/paper.pdf", verify_crossref=True, max_crossref_calls=5)

        self.assertEqual(result["total_pages"], 5)
        self.assertEqual(result["citations_in_text"], [1])
        self.assertEqual(result["total_references"], 1)
        self.assertEqual(result["citations_missing_from_references"], [])
        self.assertEqual(result["unused_references"], [])
        self.assertEqual(result["crossref_checked"], 1)
        self.assertEqual(result["crossref_verified_count"], 1)
        self.assertEqual(result["summary"], "summary text")
        self.assertEqual(result["recommendations"], ["rec 1"])
        self.assertEqual(result["references"][0]["authors"], "F. Lastname")

    def test_crossref_disabled_skips_doi_verification(self):
        full_text = 'A Paper Title\nAbstract\n...\nSee [1] for details.\nReferences\n[1] F. Lastname, "A Cited Paper," Journal, 2020.\n'
        parsed_ref = {
            "authors": "F. Lastname", "title": "A Cited Paper", "source": "Journal",
            "year": "2020", "doi": "10.1109/EXAMPLE.2020.1", "url": "", "volume": "", "issue": "", "pages": "",
            "extraction_method": "ai", "extraction_confidence": 0.9,
        }
        with patch(f"{_ANALYZER}.extract_text_from_file", return_value=(full_text, 1, "pdf")), \
             patch(f"{_ANALYZER}.find_references_section", return_value="References\n[1] ...\n"), \
             patch(f"{_ANALYZER}.split_references_section", return_value=[(1, 'F. Lastname, "A Cited Paper," Journal, 2020.')]), \
             patch(f"{_ANALYZER}.extract_reference_fields", return_value=parsed_ref), \
             patch(f"{_ANALYZER}.validate_ieee_format_ai", return_value=[]), \
             patch(f"{_ANALYZER}.verify_doi") as mock_verify_doi, \
             patch(f"{_ANALYZER}.check_paper_structure", return_value={
                 "detected_sections": [], "missing_required_sections": ["Conclusion"],
                 "section_order_valid": True, "structure_score": 75.0,
             }), \
             patch(f"{_ANALYZER}.find_citation_mismatches", return_value=[]), \
             patch(f"{_ANALYZER}.generate_recommendations_and_summary_ai", return_value=("summary text", ["rec 1"])):
            result = perform_ieee_analysis("/tmp/paper.pdf", verify_crossref=False)

        mock_verify_doi.assert_not_called()
        self.assertEqual(result["crossref_checked"], 0)

    def test_missing_and_unused_citations_detected(self):
        # reference 3 is deliberately written without a "[3]" bracket marker in its own
        # listing text - extract_in_text_citations scans the WHOLE document including the
        # reference list itself, so a bracketed "[3] ..." entry would count as its own
        # in-text citation and this test's premise (reference 3 is never cited) would break.
        full_text = "A Paper Title\nAbstract\n...\nSee [1] and [2] for details.\nReferences\n[1] F. Lastname, \"A Cited Paper,\" Journal, 2020.\n3. Another entry never cited in text, 2019.\n"
        parsed_ref_1 = {
            "authors": "F. Lastname", "title": "A Cited Paper", "source": "Journal", "year": "2020",
            "doi": "", "url": "", "volume": "", "issue": "", "pages": "",
            "extraction_method": "regex_fallback", "extraction_confidence": 0.0,
        }
        parsed_ref_3 = {
            "authors": "", "title": "", "source": "", "year": "2019",
            "doi": "", "url": "", "volume": "", "issue": "", "pages": "",
            "extraction_method": "regex_fallback", "extraction_confidence": 0.0,
        }

        with patch(f"{_ANALYZER}.extract_text_from_file", return_value=(full_text, 1, "pdf")), \
             patch(f"{_ANALYZER}.find_references_section", return_value="References\n...\n"), \
             patch(f"{_ANALYZER}.split_references_section", return_value=[
                 (1, 'F. Lastname, "A Cited Paper," Journal, 2020.'),
                 (3, "Another entry never cited in text, 2019."),
             ]), \
             patch(f"{_ANALYZER}.extract_reference_fields", side_effect=[parsed_ref_1, parsed_ref_3]), \
             patch(f"{_ANALYZER}.validate_ieee_format_ai", return_value=[]), \
             patch(f"{_ANALYZER}.check_paper_structure", return_value={
                 "detected_sections": [], "missing_required_sections": [],
                 "section_order_valid": True, "structure_score": 100.0,
             }), \
             patch(f"{_ANALYZER}.find_citation_mismatches", return_value=[]), \
             patch(f"{_ANALYZER}.generate_recommendations_and_summary_ai", return_value=("summary", [])):
            result = perform_ieee_analysis("/tmp/paper.pdf", verify_crossref=False)

        self.assertEqual(result["citations_missing_from_references"], [2])
        self.assertEqual(result["unused_references"], [3])
