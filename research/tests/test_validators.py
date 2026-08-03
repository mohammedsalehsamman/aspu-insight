from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from research.validators import validate_file_size


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
