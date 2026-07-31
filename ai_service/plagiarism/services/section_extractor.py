import re

# استخراج "جوهر البحث العلمي" فقط (الملخص، النتائج، المنهجية/الخوارزميات المستخدمة) قبل تقسيم
# النص لمقارنة الانتحال — لا الإهداء والشكر والفهرس ومقدمات عامة. هذه الأقسام تتشابه صياغياً بين
# أي رسالتين جامعيتين بغض النظر عن الموضوع (تأكَّد تجريبياً على أوراق حقيقية مستقلة من الإنترنت:
# رسالة محاسبة ورسالة طبية غير مرتبطتين إطلاقاً سجّلتا 96.5% تشابهاً "مؤكَّداً" بسبب قوالب عامة
# مشتركة)، بينما جوهر البحث الفعلي هو ما يميّز عملاً عن آخر فعلياً.

# عربي — جوهر البحث (يُبقى)
_TARGET_PATTERNS_AR = [
    re.compile(r'^(ال)?ملخص\b'),
    re.compile(r'^المستخلص\b'),
    re.compile(r'^خلاصة\s+(الدراسة|البحث)\b'),
    re.compile(r'^(ال)?نتائج\b'),
    re.compile(r'^عرض\s+(و\s*تحليل\s+)?النتائج\b'),
    re.compile(r'^(منهج|منهجية)\s'),
    re.compile(r'^طريقة\s+(البحث|الدراسة)\b'),
    re.compile(r'^ادوات\s+الدراسة\b'),
    re.compile(r'^الخوارزمي'),
    re.compile(r'^المناقشة\b'),
]

# English — core substance (kept). The service also handles English-language papers.
_TARGET_PATTERNS_EN = [
    re.compile(r'^abstract\b', re.IGNORECASE),
    re.compile(r'^summary\b', re.IGNORECASE),
    re.compile(r'^executive\s+summary\b', re.IGNORECASE),
    re.compile(r'^results?\b', re.IGNORECASE),
    re.compile(r'^findings\b', re.IGNORECASE),
    re.compile(r'^(results?\s+and\s+discussion)\b', re.IGNORECASE),
    re.compile(r'^methodology\b', re.IGNORECASE),
    re.compile(r'^method(s)?\b', re.IGNORECASE),
    re.compile(r'^materials?\s+and\s+methods?\b', re.IGNORECASE),
    re.compile(r'^research\s+method(ology)?\b', re.IGNORECASE),
    re.compile(r'^algorithm(s)?\b', re.IGNORECASE),
    re.compile(r'^discussion\b', re.IGNORECASE),
]

_TARGET_PATTERNS = _TARGET_PATTERNS_AR + _TARGET_PATTERNS_EN

# عربي — أقسام تُستبعَد (حدود فقط، لا تُقتبَس محتوياتها)
_EXCLUDED_HEADING_PATTERNS_AR = [
    re.compile(r'^الاهداء\b'),
    re.compile(r'^شكر\b'),  # يغطي "شكر وتقدير" و"شكر وعرفان" وأي صيغة أخرى — الكلمة الأولى وحدها كافية
    re.compile(r'^كلمة\s+شكر\b'),
    re.compile(r'^قائمة\s+(المحتويات|الجداول|الاشكال|الملاحق)\b'),
    re.compile(r'^(ال)?مقدمة\b'),
    re.compile(r'^(ال)?اطار\s+النظري\b'),
    re.compile(r'^الدراسات\s+السابقة\b'),
    re.compile(r'^(ال)?خاتمة\b'),
    re.compile(r'^التوصيات\b'),
    re.compile(r'^(ال)?مراجع\b'),
    re.compile(r'^الملاحق\b'),
    re.compile(r'^الفهرس\b'),
]

# English — excluded sections (boundary markers only, content never extracted)
_EXCLUDED_HEADING_PATTERNS_EN = [
    re.compile(r'^dedication\b', re.IGNORECASE),
    re.compile(r'^acknowledge?ment(s)?\b', re.IGNORECASE),
    re.compile(r'^(table\s+of\s+contents|list\s+of\s+(tables|figures|abbreviations))\b', re.IGNORECASE),
    re.compile(r'^introduction\b', re.IGNORECASE),
    re.compile(r'^(literature\s+review|related\s+work|theoretical\s+framework|background)\b', re.IGNORECASE),
    re.compile(r'^conclusion(s)?\b', re.IGNORECASE),
    re.compile(r'^recommendations?\b', re.IGNORECASE),
    re.compile(r'^(references|bibliography|works\s+cited)\b', re.IGNORECASE),
    re.compile(r'^appendi(x|ces)\b', re.IGNORECASE),
    re.compile(r'^index\b', re.IGNORECASE),
]

_ALL_HEADING_PATTERNS = (
    _TARGET_PATTERNS + _EXCLUDED_HEADING_PATTERNS_AR + _EXCLUDED_HEADING_PATTERNS_EN
)

_MAX_HEADING_LINE_LENGTH = 60
_MIN_EXTRACTED_LENGTH = 300

# استخراج العناوين من نص PDF مُستخرَج آلياً غالباً ما يُسقِط الهمزات (الإهداء ← الاهداء، إطار ← اطار)
# أو يبدّلها بشكل غير منتظم — تُوحَّد كل صور الألف قبل المطابقة بدل الاعتماد على إملاء واحد دقيق.
_ALEF_VARIANTS_RE = re.compile(r'[أإآ]')


def _normalize_arabic(text):
    return _ALEF_VARIANTS_RE.sub('ا', text)


def _is_heading(line, patterns):
    line = _normalize_arabic(line.strip())
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
