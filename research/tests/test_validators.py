from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from research.validators import validate_file_size, validate_pdf_content
from tests_common.files import (
    make_corrupt_pdf_bytes,
    make_empty_pdf_bytes,
    make_valid_pdf_bytes,
    make_wrong_magic_bytes,
)


class FakeFile:
    """Minimal stand-in for an UploadedFile — validate_file_size only reads .size."""

    def __init__(self, size):
        self.size = size


class ValidateFileSizeTests(SimpleTestCase):

    def test_file_well_under_limit_passes(self):
        try:
            validate_file_size(FakeFile(1024))
        except ValidationError:
            self.fail("validate_file_size raised ValidationError for a small file")

    def test_file_exactly_at_limit_passes(self):
        # Boundary: filesize > 5242880 raises, so exactly 5242880 must pass.
        try:
            validate_file_size(FakeFile(5242880))
        except ValidationError:
            self.fail("validate_file_size raised ValidationError for a file exactly at the limit")

    def test_file_one_byte_over_limit_raises(self):
        with self.assertRaises(ValidationError):
            validate_file_size(FakeFile(5242881))

    def test_file_well_over_limit_raises(self):
        with self.assertRaises(ValidationError):
            validate_file_size(FakeFile(10 * 1024 * 1024))

    def test_zero_size_file_passes(self):
        try:
            validate_file_size(FakeFile(0))
        except ValidationError:
            self.fail("validate_file_size raised ValidationError for a zero-byte file")


class ValidatePdfContentTests(SimpleTestCase):
    def _uploaded(self, data, name='paper.pdf'):
        return SimpleUploadedFile(name, data, content_type='application/pdf')

    def test_valid_single_page_pdf_passes(self):
        try:
            validate_pdf_content(self._uploaded(make_valid_pdf_bytes(1)))
        except ValidationError:
            self.fail("validate_pdf_content raised ValidationError for a valid PDF")

    def test_valid_multi_page_pdf_passes(self):
        try:
            validate_pdf_content(self._uploaded(make_valid_pdf_bytes(3)))
        except ValidationError:
            self.fail("validate_pdf_content raised ValidationError for a valid multi-page PDF")

    def test_wrong_magic_bytes_raises(self):
        with self.assertRaises(ValidationError):
            validate_pdf_content(self._uploaded(make_wrong_magic_bytes()))

    def test_correct_header_but_corrupt_structure_raises(self):
        with self.assertRaises(ValidationError):
            validate_pdf_content(self._uploaded(make_corrupt_pdf_bytes()))

    def test_zero_page_pdf_raises(self):
        with self.assertRaises(ValidationError):
            validate_pdf_content(self._uploaded(make_empty_pdf_bytes()))

    def test_leaves_file_pointer_at_start_after_success(self):
        uploaded = self._uploaded(make_valid_pdf_bytes(1))
        validate_pdf_content(uploaded)
        self.assertEqual(uploaded.tell(), 0)
