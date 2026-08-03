from docx import Document
from pypdf import PdfReader
from pypdf.errors import PdfReadError


def validate_pdf_or_docx_content(uploaded_file) -> str | None:
    """يرجع رسالة خطأ عربية إن كان المحتوى غير صالح، أو None إن كان سليماً."""
    name_lower = uploaded_file.name.lower()
    uploaded_file.seek(0)
    header = uploaded_file.read(8)
    uploaded_file.seek(0)

    if name_lower.endswith('.pdf'):
        if not header.startswith(b'%PDF-'):
            return "الملف ليس بصيغة PDF فعلية رغم امتداده."
        try:
            if len(PdfReader(uploaded_file).pages) == 0:
                return "ملف PDF فارغ أو تالف."
        except PdfReadError:
            return "تعذّر قراءة ملف PDF — الملف تالف أو غير صالح."
        finally:
            uploaded_file.seek(0)
        return None

    if name_lower.endswith('.docx'):
        if not header.startswith(b'PK'):
            return "الملف ليس بصيغة DOCX فعلية رغم امتداده."
        try:
            Document(uploaded_file)
        except Exception:
            return "تعذّر قراءة ملف DOCX — الملف تالف أو غير صالح."
        finally:
            uploaded_file.seek(0)
        return None

    return "يُقبل ملف PDF (.pdf) أو DOCX (.docx) فقط"
