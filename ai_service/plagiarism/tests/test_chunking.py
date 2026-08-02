from django.test import TestCase, override_settings

from ai_service.plagiarism.services.chunking import chunk_text, is_citation_chunk


class ChunkTextTests(TestCase):
    def test_empty_input_returns_empty_list(self):
        self.assertEqual(chunk_text(""), [])
        self.assertEqual(chunk_text(None), [])

    @override_settings(PLAGIARISM_CHUNK_SENTENCES=4, PLAGIARISM_CHUNK_OVERLAP=1)
    def test_produces_overlapping_windows(self):
        sentences = [f"جملة رقم {i}." for i in range(1, 9)]
        text = " ".join(sentences)
        chunks = chunk_text(text)
        # 8 sentences, window=4, step=3 (4-1 overlap) -> windows starting at 0,3,6 -> 3 chunks
        self.assertEqual(len(chunks), 3)
        # consecutive chunks must share the overlapping sentence
        self.assertIn("جملة رقم 4.", chunks[0])
        self.assertIn("جملة رقم 4.", chunks[1])

    @override_settings(PLAGIARISM_CHUNK_SENTENCES=1, PLAGIARISM_CHUNK_OVERLAP=0)
    def test_single_sentence_window_no_overlap(self):
        text = "الأولى. الثانية. الثالثة."
        chunks = chunk_text(text)
        self.assertEqual(len(chunks), 3)

    def test_short_text_returns_single_chunk(self):
        chunks = chunk_text("جملة واحدة فقط.")
        self.assertEqual(len(chunks), 1)


class IsCitationChunkTests(TestCase):
    def test_plain_text_not_flagged(self):
        text = "هذا نص عادي كتبه الباحث بنفسه دون أي اقتباس مباشر من مصدر آخر."
        self.assertFalse(is_citation_chunk(text))

    def test_quote_with_ieee_bracket_marker_flagged(self):
        text = 'ذكر الباحث أن "هذا نص مقتبس حرفياً من مصدر خارجي معروف" [3].'
        self.assertTrue(is_citation_chunk(text))

    def test_quote_with_apa_year_marker_flagged(self):
        text = '"هذا اقتباس واضح من دراسة سابقة موثوقة تماما" (Smith, 2020).'
        self.assertTrue(is_citation_chunk(text))

    def test_quote_without_citation_marker_not_flagged(self):
        # quotation marks alone (e.g. quoting a study participant, not a reference) should not trigger
        text = 'قال أحد المشاركين: "أشعر أن هذا البرنامج مفيد جدا بالنسبة لي".'
        self.assertFalse(is_citation_chunk(text))

    def test_citation_marker_without_quote_not_flagged(self):
        # a bare [3] reference marker with no quotation marks is a normal in-text citation,
        # not a verbatim quotation that needs excluding
        text = "استخدم الباحث نفس المنهجية المتبعة في دراسات سابقة [3] لتحليل البيانات."
        self.assertFalse(is_citation_chunk(text))

    def test_english_phrase_marker_flagged(self):
        text = 'According to "the original source text quoted here directly", results varied.'
        self.assertTrue(is_citation_chunk(text))

    def test_arabic_phrase_marker_flagged(self):
        text = 'نقلاً عن "نص مقتبس حرفياً هنا بالكامل من ذلك المصدر تحديدا".'
        self.assertTrue(is_citation_chunk(text))

    def test_quranic_ligature_glyphs_flagged(self):
        # Arabic Presentation Forms-A/B glyphs (U+FB50-FDFF, U+FE70-FEFF) are the artifact left by
        # PDF-extracted Quranic-typeset (Uthmanic font) text - >=5 such glyphs is a strong signal.
        ligature_glyphs = "ﭐﭑﭒﭓﭔﭕ"
        text = f"بعض النص العادي {ligature_glyphs} وبقية الفقرة هنا."
        self.assertTrue(is_citation_chunk(text))

    def test_few_quranic_ligature_glyphs_not_flagged(self):
        # below the minimum count threshold - could be an incidental stray character, not proof
        # of a full Quranic-typeset excerpt
        text = "نص عادي فيه رمز واحد فقط ﭐ من نطاق أشكال العرض العربية."
        self.assertFalse(is_citation_chunk(text))

    def test_empty_text_not_flagged(self):
        self.assertFalse(is_citation_chunk(""))
        self.assertFalse(is_citation_chunk(None))
