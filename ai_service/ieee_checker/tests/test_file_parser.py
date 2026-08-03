from unittest.mock import patch

from django.test import SimpleTestCase

from ai_service.ieee_checker.infrastructure.file_parser import extract_text_from_file


class ExtractTextFromFileTests(SimpleTestCase):
    def test_pdf_extension_routes_to_pdf_extractor(self):
        with patch(
            "ai_service.ieee_checker.infrastructure.file_parser.extract_text_from_pdf",
            return_value=("pdf content", 3),
        ) as mock_pdf:
            text, pages, kind = extract_text_from_file("/tmp/paper.pdf")
        mock_pdf.assert_called_once_with("/tmp/paper.pdf")
        self.assertEqual((text, pages, kind), ("pdf content", 3, "pdf"))

    def test_docx_extension_routes_to_docx_extractor(self):
        with patch(
            "ai_service.ieee_checker.infrastructure.file_parser.extract_text_from_docx",
            return_value=("docx content", 1),
        ) as mock_docx:
            text, pages, kind = extract_text_from_file("/tmp/paper.docx")
        mock_docx.assert_called_once_with("/tmp/paper.docx")
        self.assertEqual((text, pages, kind), ("docx content", 1, "docx"))

    def test_unsupported_extension_returns_unknown(self):
        text, pages, kind = extract_text_from_file("/tmp/paper.txt")
        self.assertEqual((text, pages, kind), ("", 0, "unknown"))

    def test_pdf_extraction_failure_is_handled_gracefully(self):
        text, pages, kind = extract_text_from_file("/nonexistent/path/does_not_exist.pdf")
        self.assertEqual((text, pages, kind), ("", 0, "pdf"))
