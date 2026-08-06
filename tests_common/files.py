import io

from docx import Document
from pypdf import PdfWriter


def make_valid_pdf_bytes(pages=1):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_empty_pdf_bytes():
    writer = PdfWriter()
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_corrupt_pdf_bytes():
    return b'%PDF-1.7\n%this is not a real xref table or object stream, just garbage\n%%EOF'


def make_wrong_magic_bytes():
    return b'this is a plain text file with a .pdf extension slapped on it'


def make_valid_docx_bytes():
    document = Document()
    document.add_paragraph('Test document content.')
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def make_corrupt_docx_bytes():
    return b'PK\x03\x04' + b'not actually a valid zip/docx structure after the magic bytes'
