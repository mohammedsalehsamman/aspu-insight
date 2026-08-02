from unittest.mock import patch

import numpy as np
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from research.models import PaperChunkEmbedding, ResearchPaper
from ai_service.plagiarism.services.internal_similarity import find_internal_matches

User = get_user_model()

# 4-dimensional hand-crafted vectors kept small and dimension-agnostic on purpose, so these
# tests never need the real (384-dim) embedding model or the real commonness bootstrap file -
# every _bootstrap_commonness_reference() call is patched to return an empty pool.
HIGH_SIM_A = [1.0, 0.0, 0.0, 0.0]
HIGH_SIM_B = [0.99, 0.02, 0.0, 0.0]      # cosine ~0.999 with HIGH_SIM_A
MODERATE_SIM = [0.85, 0.4, 0.0, 0.0]     # cosine ~0.90 with HIGH_SIM_A - above corroboration (0.50) too
LOW_SIM = [0.0, 1.0, 0.0, 0.0]           # orthogonal to HIGH_SIM_A - cosine 0.0
BELOW_SUSPECTED = [0.1, 0.995, 0.0, 0.0]  # cosine ~0.10 with HIGH_SIM_A


def _make_paper(email, title="Test Paper", specialization="accounting"):
    user = User.objects.create(email=email, full_name="Test Author", specialization=specialization)
    return ResearchPaper.objects.create(
        title=title, abstract="test", author=user, specialization=specialization
    )


def _store_other_paper_chunks(paper, chunk_specs):
    """chunk_specs: list of (text, ft_vector, base_vector, language, is_citation)"""
    PaperChunkEmbedding.objects.bulk_create([
        PaperChunkEmbedding(
            paper=paper, chunk_index=i, chunk_text=text,
            embedding_vector=ft_vec, base_embedding_vector=base_vec,
            detected_language=lang, is_citation=is_cite,
        )
        for i, (text, ft_vec, base_vec, lang, is_cite) in enumerate(chunk_specs)
    ])


@override_settings(
    PLAGIARISM_INTERNAL_SIMILARITY_THRESHOLD=0.75,
    PLAGIARISM_SUSPECTED_INTERNAL_THRESHOLD=0.25,
    PLAGIARISM_CORROBORATION_THRESHOLD=0.50,
    PLAGIARISM_MIN_CORROBORATING_CHUNKS=2,
    PLAGIARISM_MIN_CHUNKS_FOR_CORROBORATION=4,
    PLAGIARISM_COMMONNESS_THRESHOLD=0.97,
    PLAGIARISM_COMMONNESS_MAX_COUNT=5,
)
@patch(
    "ai_service.plagiarism.services.internal_similarity._bootstrap_commonness_reference",
    return_value=np.zeros((0, 4)),
)
class FindInternalMatchesTests(TestCase):
    def setUp(self):
        self.own_paper = _make_paper("own@example.com", "Own Paper")
        self.other_paper = _make_paper("other@example.com", "Other Paper")

    def test_confirmed_with_sufficient_corroboration(self, _mock_bootstrap):
        # 5 own chunks (>= the 4-chunk corroboration cutoff): 2 of them strongly match the
        # other paper's chunks, satisfying MIN_CORROBORATING_CHUNKS=2.
        own_chunks = ["own chunk %d" % i for i in range(5)]
        own_ft = [HIGH_SIM_A, HIGH_SIM_B, LOW_SIM, LOW_SIM, LOW_SIM]
        own_base = own_ft
        own_langs = ["ar"] * 5

        _store_other_paper_chunks(self.other_paper, [
            ("other chunk 0", HIGH_SIM_A, HIGH_SIM_A, "ar", False),
            ("other chunk 1", HIGH_SIM_A, HIGH_SIM_A, "ar", False),
        ])

        matches = find_internal_matches(self.own_paper, own_chunks, own_ft, own_base, own_langs)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["confidence_level"], "confirmed")
        self.assertEqual(matches[0]["matched_paper"], self.other_paper)

    def test_suspected_when_corroboration_insufficient(self, _mock_bootstrap):
        # same top score as above, but only ONE own chunk matches strongly - the rest are
        # unrelated, so the 2-chunk corroboration requirement is not met.
        own_chunks = ["own chunk %d" % i for i in range(5)]
        own_ft = [HIGH_SIM_A, LOW_SIM, LOW_SIM, LOW_SIM, LOW_SIM]
        own_base = own_ft
        own_langs = ["ar"] * 5

        _store_other_paper_chunks(self.other_paper, [
            ("other chunk 0", HIGH_SIM_A, HIGH_SIM_A, "ar", False),
        ])

        matches = find_internal_matches(self.own_paper, own_chunks, own_ft, own_base, own_langs)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["confidence_level"], "suspected")

    def test_bypasses_corroboration_for_short_papers(self, _mock_bootstrap):
        # regression test for this session's fix: a paper with FEWER than
        # PLAGIARISM_MIN_CHUNKS_FOR_CORROBORATION chunks (here: 2) should be confirmed on a
        # single strong match alone, since requiring 2 corroborating chunks out of only 2
        # total chunks is not a meaningful bar.
        own_chunks = ["own chunk 0", "own chunk 1"]
        own_ft = [HIGH_SIM_A, LOW_SIM]
        own_base = own_ft
        own_langs = ["ar", "ar"]

        _store_other_paper_chunks(self.other_paper, [
            ("other chunk 0", HIGH_SIM_A, HIGH_SIM_A, "ar", False),
        ])

        matches = find_internal_matches(self.own_paper, own_chunks, own_ft, own_base, own_langs)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["confidence_level"], "confirmed")

    def test_citation_chunks_excluded_from_comparison(self, _mock_bootstrap):
        # the own paper's ONLY strongly-matching chunk is a declared quotation; it must be
        # excluded, leaving no genuine match against the (otherwise unrelated) other paper.
        own_chunks = [
            'كما ورد في "هذا اقتباس حرفي محدد من مصدر خارجي معروف تماما" [1].',
            "هذا مقطع أصلي عادي من كتابة الباحث نفسه دون أي اقتباس.",
        ]
        own_ft = [HIGH_SIM_A, LOW_SIM]
        own_base = own_ft
        own_langs = ["ar", "ar"]

        _store_other_paper_chunks(self.other_paper, [
            ("other chunk 0", HIGH_SIM_A, HIGH_SIM_A, "ar", False),
        ])

        matches = find_internal_matches(self.own_paper, own_chunks, own_ft, own_base, own_langs)
        self.assertEqual(matches, [])

    def test_no_match_below_suspected_threshold(self, _mock_bootstrap):
        own_chunks = ["own chunk 0"]
        own_ft = [BELOW_SUSPECTED]
        own_base = own_ft
        own_langs = ["ar"]

        _store_other_paper_chunks(self.other_paper, [
            ("other chunk 0", HIGH_SIM_A, HIGH_SIM_A, "ar", False),
        ])

        matches = find_internal_matches(self.own_paper, own_chunks, own_ft, own_base, own_langs)
        self.assertEqual(matches, [])

    def test_other_papers_citation_chunks_excluded(self, _mock_bootstrap):
        # the other paper's only strongly-matching row is itself a declared quotation and
        # must be excluded from being a usable match target.
        own_chunks = ["own chunk 0"]
        own_ft = [HIGH_SIM_A]
        own_base = own_ft
        own_langs = ["ar"]

        _store_other_paper_chunks(self.other_paper, [
            ("other chunk 0", HIGH_SIM_A, HIGH_SIM_A, "ar", True),
        ])

        matches = find_internal_matches(self.own_paper, own_chunks, own_ft, own_base, own_langs)
        self.assertEqual(matches, [])

    def test_cross_language_pair_uses_base_vectors_not_finetuned(self, _mock_bootstrap):
        # own chunk and other chunk are both English ("en", not "ar") - the shared
        # fine-tuned (Arabic-specific) space must NOT be used for this pair; only the base
        # embedding space should decide the match. Finetuned vectors are deliberately set to
        # look unrelated while base vectors look identical, so a match only appears if base
        # was genuinely used.
        own_chunks = ["own english chunk"]
        own_ft = [LOW_SIM]
        own_base = [HIGH_SIM_A]
        own_langs = ["en"]

        _store_other_paper_chunks(self.other_paper, [
            ("other english chunk", LOW_SIM, HIGH_SIM_A, "en", False),
        ])

        matches = find_internal_matches(self.own_paper, own_chunks, own_ft, own_base, own_langs)
        self.assertEqual(len(matches), 1)
        self.assertAlmostEqual(matches[0]["score"], 1.0, places=2)

    def test_empty_chunks_returns_no_matches(self, _mock_bootstrap):
        matches = find_internal_matches(self.own_paper, [], None, None, [])
        self.assertEqual(matches, [])

    def test_own_paper_excluded_from_its_own_matches(self, _mock_bootstrap):
        # store chunk-embedding rows for the OWN paper too (as store_chunk_embeddings would)
        # and confirm find_internal_matches never matches a paper against itself.
        _store_other_paper_chunks(self.own_paper, [
            ("own stored chunk", HIGH_SIM_A, HIGH_SIM_A, "ar", False),
        ])
        own_chunks = ["own chunk 0"]
        own_ft = [HIGH_SIM_A]
        own_base = own_ft
        own_langs = ["ar"]

        matches = find_internal_matches(self.own_paper, own_chunks, own_ft, own_base, own_langs)
        self.assertEqual(matches, [])
