from django.test import SimpleTestCase

from ai_service.ieee_checker.services.reference_parser import (
    find_references_section,
    parse_ieee_reference,
    split_references_section,
)


class FindReferencesSectionTests(SimpleTestCase):
    def test_no_references_heading_returns_empty_string(self):
        self.assertEqual(find_references_section("Just some body text with no reference list."), "")

    def test_extracts_from_last_references_heading_onward(self):
        text = "Body text mentioning References in passing.\nReferences\n[1] Some entry here, 2020."
        section = find_references_section(text)
        self.assertTrue(section.startswith("References"))

    def test_stops_at_appendix_marker(self):
        text = (
            "References\n"
            "[1] A. Author, \"Some Title,\" Journal, 2020.\n"
            + ("padding text to push past the first fifty characters. " * 3)
            + "\nAppendix\nExtra appendix content that should not be included."
        )
        section = find_references_section(text)
        self.assertNotIn("Extra appendix content", section)


class SplitReferencesSectionTests(SimpleTestCase):
    def test_splits_numbered_bracket_references(self):
        section = (
            "References\n"
            "[1] A. Smith, \"A Great Study of Systems,\" IEEE Trans., vol. 1, 2020.\n"
            "[2] B. Jones, \"Another Great Study,\" ACM Journal, 2021.\n"
        )
        refs = split_references_section(section)
        self.assertEqual([r[0] for r in refs], [1, 2])

    def test_rejects_short_or_invalid_entries(self):
        section = "References\n[1] Too short.\n[2] Figure 1 shows an unrelated caption fragment here.\n"
        refs = split_references_section(section)
        self.assertEqual(refs, [])

    def test_rejects_reference_numbers_above_999(self):
        section = 'References\n[1000] A. Smith, "A Valid Looking Title Here," Journal, 2020.\n'
        refs = split_references_section(section)
        self.assertEqual(refs, [])


class ParseIeeeReferenceTests(SimpleTestCase):
    def test_full_ieee_style_reference_parsed(self):
        ref_text = 'F. Lastname, "A Great Paper Title," IEEE Transactions, vol. 3, no. 2, pp. 12-20, 2021.'
        parsed = parse_ieee_reference(ref_text)
        # the trailing comma is part of the quoted span in true IEEE style ("Title,") and is
        # captured as-is; the parser does not strip trailing punctuation from the title.
        self.assertEqual(parsed["title"], "A Great Paper Title,")
        self.assertEqual(parsed["year"], "2021")
        self.assertEqual(parsed["volume"], "3")
        self.assertEqual(parsed["issue"], "2")
        self.assertEqual(parsed["pages"], "12-20")
        self.assertIn("F. Lastname", parsed["authors"])

    def test_doi_extracted(self):
        ref_text = 'A. Author, "A Title," Journal, 2020. doi: 10.1109/EXAMPLE.2020.123'
        parsed = parse_ieee_reference(ref_text)
        self.assertEqual(parsed["doi"], "10.1109/EXAMPLE.2020.123")

    def test_url_extracted(self):
        ref_text = "See https://example.com/paper for the full reference details, 2019."
        parsed = parse_ieee_reference(ref_text)
        self.assertEqual(parsed["url"], "https://example.com/paper")

    def test_arxiv_id_not_mistaken_for_year(self):
        ref_text = "A. Author, arXiv:2101.00001, published in 2019."
        parsed = parse_ieee_reference(ref_text)
        self.assertEqual(parsed["year"], "2019")

    def test_arabic_authors_without_quoted_title_extracted(self):
        ref_text = "محمد أحمد، عنوان الدراسة بدون علامات اقتباس، مجلة الأبحاث، 2020."
        parsed = parse_ieee_reference(ref_text)
        self.assertIn("محمد أحمد", parsed["authors"])

    def test_no_year_or_doi_leaves_fields_empty(self):
        ref_text = "Some reference text without any recognizable structured fields at all"
        parsed = parse_ieee_reference(ref_text)
        self.assertEqual(parsed["year"], "")
        self.assertEqual(parsed["doi"], "")
