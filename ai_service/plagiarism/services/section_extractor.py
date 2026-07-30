import re

# استخراج "جوهر البحث العلمي" فقط (الملخص، النتائج، المنهجية/الخوارزميات المستخدمة) قبل تقسيم
# النص لمقارنة الانتحال — لا الإهداء والشكر والفهرس ومقدمات عامة. هذه الأقسام تتشابه صياغياً بين
# أي رسالتين جامعيتين بغض النظر عن الموضوع (تأكَّد تجريبياً على أوراق حقيقية مستقلة من الإنترنت:
# رسالة محاسبة ورسالة طبية غير مرتبطتين إطلاقاً سجّلتا 96.5% تشابهاً "مؤكَّداً" بسبب قوالب عامة
# مشتركة)، بينما جوهر البحث الفعلي هو ما يميّز عملاً عن آخر فعلياً.

_TARGET_PATTERNS = [
    re.compile(r'^(ال)?ملخص\b'),
    re.compile(r'^المستخلص\b'),
    re.compile(r'^خلاصة\s+(الدراسة|البحث)\b'),
    re.compile(r'^(ال)?نتائج\b'),
    re.compile(r'^عرض\s+(و\s*تحليل\s+)?النتائج\b'),
    re.compile(r'^(منهج|منهجية)\s'),
    re.compile(r'^طريقة\s+(البحث|الدراسة)\b'),
    re.compile(r'^أدوات\s+الدراسة\b'),
    re.compile(r'^الخوارزمي'),
    re.compile(r'^المناقشة\b'),
]

_ALL_HEADING_PATTERNS = _TARGET_PATTERNS + [
    re.compile(r'^الإهداء\b'),
    re.compile(r'^شكر\s*(و|و\s*)?تقدير\b'),
    re.compile(r'^قائمة\s+(المحتويات|الجداول|الأشكال|الملاحق)\b'),
    re.compile(r'^(ال)?مقدمة\b'),
    re.compile(r'^(ال)?إطار\s+النظري\b'),
    re.compile(r'^الدراسات\s+السابقة\b'),
    re.compile(r'^(ال)?خاتمة\b'),
    re.compile(r'^التوصيات\b'),
    re.compile(r'^(ال)?مراجع\b'),
    re.compile(r'^الملاحق\b'),
    re.compile(r'^الفهرس\b'),
]

_MAX_HEADING_LINE_LENGTH = 60
_MIN_EXTRACTED_LENGTH = 300


def _is_heading(line, patterns):
    line = line.strip()
    if not line or len(line) > _MAX_HEADING_LINE_LENGTH:
        return False
    return any(p.search(line) for p in patterns)


def extract_core_sections(text):
    """يُرجِع نص جوهر البحث فقط (ملخص + نتائج + منهجية/خوارزميات) إن أمكن استخراجها بثقة،
    وإلا يُرجِع النص الكامل كما هو (احتياط آمن لأوراق ذات تنسيق غير قياسي)."""
    text = (text or "").strip()
    if not text:
        return text

    lines = text.split('\n')
    headings = []  # (line_index, is_target)
    for i, line in enumerate(lines):
        if _is_heading(line, _TARGET_PATTERNS):
            headings.append((i, True))
        elif _is_heading(line, _ALL_HEADING_PATTERNS):
            headings.append((i, False))

    if not any(is_target for _, is_target in headings):
        return text

    extracted = []
    for idx, (line_i, is_target) in enumerate(headings):
        if not is_target:
            continue
        end = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
        section_text = '\n'.join(lines[line_i:end]).strip()
        if section_text:
            extracted.append(section_text)

    combined = '\n\n'.join(extracted).strip()
    return combined if len(combined) >= _MIN_EXTRACTED_LENGTH else text
