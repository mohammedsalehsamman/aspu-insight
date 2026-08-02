from django.core.exceptions import ValidationError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

def validate_file_size(value):
    filesize = value.size
    if filesize > 5242880:
        raise ValidationError("الحد الأقصى لحجم الملف هو 5 ميجابايت فقط.")

def validate_pdf_content(value):
    value.seek(0)
    header = value.read(5)
    value.seek(0)
    if header != b'%PDF-':
        raise ValidationError("الملف ليس بصيغة PDF فعلية رغم امتداده.")
    try:
        reader = PdfReader(value)
        if len(reader.pages) == 0:
            raise ValidationError("ملف PDF فارغ أو تالف.")
    except PdfReadError:
        raise ValidationError("تعذّر قراءة ملف PDF — الملف تالف أو غير صالح.")
    finally:
        value.seek(0)