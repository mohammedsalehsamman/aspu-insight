from django.test import SimpleTestCase

from ai_service.claim_evidence.services.heuristics import score_sentence_heuristic


class ScoreSentenceHeuristicTests(SimpleTestCase):
    def test_plain_sentence_is_neutral(self):
        label, score = score_sentence_heuristic("The building was constructed in 1990.")
        self.assertEqual(label, "neutral")
        self.assertEqual(score, 0.0)

    def test_english_claim_cue_detected(self):
        label, _ = score_sentence_heuristic("We propose a new method for detecting anomalies.")
        self.assertEqual(label, "claim")

    def test_english_evidence_cue_detected(self):
        label, _ = score_sentence_heuristic("Results show a significant improvement in accuracy.")
        self.assertEqual(label, "evidence")

    def test_arabic_claim_cue_detected(self):
        label, _ = score_sentence_heuristic("نقترح منهجية جديدة لتحليل البيانات في هذا البحث.")
        self.assertEqual(label, "claim")

    def test_arabic_evidence_cue_detected(self):
        label, _ = score_sentence_heuristic("أظهرت النتائج تحسناً واضحاً في دقة النموذج المقترح.")
        self.assertEqual(label, "evidence")

    def test_percentage_numeric_pattern_boosts_evidence(self):
        label, _ = score_sentence_heuristic("The accuracy improved by 25% after tuning.")
        self.assertEqual(label, "evidence")

    def test_table_figure_reference_boosts_evidence(self):
        label, _ = score_sentence_heuristic("As shown in Table 3, the results vary considerably.")
        self.assertEqual(label, "evidence")

    def test_tied_claim_and_evidence_scores_return_neutral(self):
        # exactly one claim cue and one evidence cue -> tie -> neutral by design
        label, score = score_sentence_heuristic("We propose that results show promise.")
        self.assertEqual(label, "neutral")
        self.assertEqual(score, 0.0)

    def test_score_is_capped_at_point_three(self):
        text = "We propose, we argue, we claim, we hypothesize, we believe this suggests this indicates."
        _, score = score_sentence_heuristic(text)
        self.assertLessEqual(score, 0.3)
