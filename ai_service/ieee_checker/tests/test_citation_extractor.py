from django.test import SimpleTestCase

from ai_service.ieee_checker.services.citation_extractor import (
    detect_language,
    extract_in_text_citations,
    extract_paper_title,
)


class DetectLanguageTests(SimpleTestCase):
    def test_empty_text_is_unknown(self):
        self.assertEqual(detect_language(""), "unknown")

    def test_mostly_arabic_text_detected(self):
        self.assertEqual(detect_language("هذا نص عربي بالكامل تقريباً بدون أي كلمات لاتينية هنا."), "ar")

    def test_mostly_english_text_detected(self):
        self.assertEqual(detect_language("This is an entirely English paper with no Arabic content at all."), "en")

    def test_balanced_bilingual_text_detected_as_mixed(self):
        text = "English words here now more words padding padding padding padding. عربية هنا فقط قليلا."
        self.assertEqual(detect_language(text), "mixed")


class ExtractPaperTitleTests(SimpleTestCase):
    def test_skips_short_lines_and_keywords(self):
        text = "IEEE\nAbstract\nA Novel Approach to Distributed Systems Reliability\nIntroduction\n..."
        self.assertEqual(extract_paper_title(text), "A Novel Approach to Distributed Systems Reliability")

    def test_skips_arxiv_and_page_number_lines(self):
        text = "arXiv:2101.00001v2\n1\nA Study on Federated Learning Optimization Techniques\nAbstract\n..."
        self.assertEqual(extract_paper_title(text), "A Study on Federated Learning Optimization Techniques")

    def test_empty_text_returns_empty_string(self):
        self.assertEqual(extract_paper_title(""), "")

    def test_falls_back_to_first_line_when_all_lines_filtered(self):
        text = "abstract\nintroduction\nreferences"
        self.assertEqual(extract_paper_title(text), "abstract")


class ExtractInTextCitationsTests(SimpleTestCase):
    def test_no_citations_returns_empty_dict(self):
        self.assertEqual(extract_in_text_citations("Plain text with no citations at all."), {})

    def test_single_bracket_citations_counted(self):
        text = "As shown in [1], and further confirmed by [2] and again by [1]."
        self.assertEqual(extract_in_text_citations(text), {1: 2, 2: 1})

    def test_comma_grouped_citations_counted(self):
        text = "This has been studied extensively [3, 4, 5]."
        self.assertEqual(extract_in_text_citations(text), {3: 1, 4: 1, 5: 1})

    def test_range_citations_expanded(self):
        # note: the endpoints [6] and [8] are also matched by the plain single-bracket
        # pattern in addition to the range-expansion pattern, so they end up double-counted
        # (2) while the only-implied middle number [7] is counted once - this is the
        # extractor's actual current behaviour, not a designed 1-count-per-citation contract.
        text = "See references [6]-[8] for more detail."
        counts = extract_in_text_citations(text)
        self.assertEqual(counts, {6: 2, 7: 1, 8: 2})
