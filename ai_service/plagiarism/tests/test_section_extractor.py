from django.test import TestCase

from ai_service.plagiarism.services.section_extractor import extract_core_sections


def _pad(text, n_lines=40):
    """Pads a section with enough generic body lines to clear _MIN_EXTRACTED_LENGTH,
    so the extraction result reflects real section-boundary behaviour rather than the
    'too-short overall, fall back to full text' safety branch."""
    filler = "\n".join(f"سطر محتوى عادي رقم {i} ضمن هذا القسم لتوفير طول كافٍ للاختبار." for i in range(n_lines))
    return text + "\n" + filler


class ExtractCoreSectionsTests(TestCase):
    def test_empty_text_returns_empty(self):
        self.assertEqual(extract_core_sections(""), "")
        self.assertEqual(extract_core_sections(None), "")

    def test_extracts_abstract_and_results_excludes_dedication(self):
        text = (
            "الإهداء\n" + _pad("إلى والدي العزيزين وكل من دعمني.") + "\n"
            "الملخص\n" + _pad("يتناول هذا البحث دراسة تطبيقية حول موضوع محدد.") + "\n"
            "النتائج\n" + _pad("أظهرت النتائج وجود علاقة ذات دلالة إحصائية بين المتغيرات.")
        )
        core = extract_core_sections(text)
        self.assertIn("يتناول هذا البحث", core)
        self.assertIn("أظهرت النتائج", core)
        self.assertNotIn("إلى والدي العزيزين", core)

    def test_falls_back_to_full_text_when_no_target_heading_found(self):
        # no recognizable "الملخص/النتائج/منهجية" heading anywhere - safe fallback is the
        # unmodified original text, not an empty or truncated result
        text = "نص طويل من رسالة لا تحوي أي عنوان معروف على الإطلاق. " * 20
        core = extract_core_sections(text)
        self.assertEqual(core, text.strip())

    def test_law_thesis_results_word_false_positive_regression(self):
        """Regression test for the bug found in this session's live validation: a law-thesis
        subheading using 'نتائج' to mean legal *consequences* (not empirical study results)
        must not be treated as a 'Results' section heading and swallow most of the document.
        Law theses are doctrinal/argumentative and have no empirical results section at all."""
        bad_subheading_body = _pad(
            "تناول هذا الفرع الآثار القانونية المترتبة على تطبيق قاعدة الجدة النسبية في القضاء."
        )
        text = (
            "مقدمة\n" + _pad("عرض عام لموضوع الأطروحة والإشكالية المطروحة.") + "\n"
            "النتائج المترتبة عن الجدة النسبية\n" + bad_subheading_body + "\n"
            + ("نص إضافي كثير جداً يمثل بقية فصول الأطروحة القانونية. " * 200) + "\n"
            "ملخص\n" + _pad("هذا هو الملخص الحقيقي للأطروحة القانونية.")
        )
        core = extract_core_sections(text)
        # the spurious "نتائج" match must not have pulled in the huge remainder of the document
        self.assertLess(len(core), len(text) * 0.5)

    def test_section_span_capped_at_max_lines(self):
        """Even a genuine target heading must not span unboundedly far if the next heading
        is very distant - a hard per-section line cap bounds the worst case regardless of
        why the next heading wasn't found nearby."""
        long_body = "\n".join(f"سطر رقم {i} من محتوى طويل جداً بعد عنوان النتائج مباشرة." for i in range(500))
        text = "النتائج\n" + long_body + "\nملخص\n" + _pad("ملخص قصير في نهاية الوثيقة.")
        core = extract_core_sections(text)
        # 500-line body is far larger than the section cap; extracted core must be much
        # smaller than the full 500+ line body, proving the cap actually bit
        self.assertLess(core.count("\n"), 300)

    def test_english_headings_recognized(self):
        text = (
            "Introduction\n" + _pad("General background material about the research topic.") + "\n"
            "Abstract\n" + _pad("This study investigates a specific applied research question.") + "\n"
            "Results\n" + _pad("The findings show a statistically significant relationship.")
        )
        core = extract_core_sections(text)
        self.assertIn("investigates a specific applied", core)
        self.assertIn("statistically significant", core)
        self.assertNotIn("General background material", core)

    def test_heading_like_line_with_too_many_words_rejected(self):
        """A long descriptive sentence that merely contains a target keyword (5+ words) must
        not be treated as a bare section heading - this is the general safeguard that
        replaced the first (overly strict) attempt at fixing the law-thesis regression."""
        text = (
            "النتائج المترتبة عن هذا التحليل القانوني المعقد جداً\n"
            + _pad("محتوى لا علاقة له بنتائج دراسة تجريبية إطلاقاً.") + "\n"
            "ملخص\n" + _pad("هذا هو الملخص الحقيقي القصير.")
        )
        core = extract_core_sections(text)
        self.assertNotIn("محتوى لا علاقة له", core)
