from unittest.mock import MagicMock, PropertyMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from ai_service import tasks
from ai_service.models import ClaimEvidenceGraphReport, IEEECheckReport
from research.models import PlagiarismReport, PlagiarismSource, ResearchPaper

User = get_user_model()

FIELD_FILE_PATH = "django.db.models.fields.files.FieldFile.path"


class ClaimEvidenceGraphTaskTests(TestCase):
    def setUp(self):
        self.report = ClaimEvidenceGraphReport.objects.create(
            original_filename="paper.pdf",
            similarity_threshold=0.5,
            top_claims_count=10,
        )

    def test_report_not_found_returns_failed_without_raising(self):
        result = tasks.analyze_claim_evidence_graph_task(9999)
        self.assertEqual(result, {"status": "failed", "report_id": 9999, "error": "report not found"})

    def test_empty_extracted_text_marks_failed(self):
        with patch(FIELD_FILE_PATH, new_callable=PropertyMock, return_value="fake/path.pdf"), \
             patch("ai_service.tasks.extract_text_from_file", return_value=("   ", 1, "pdf")):
            result = tasks.analyze_claim_evidence_graph_task(self.report.id)

        self.report.refresh_from_db()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.report.status, ClaimEvidenceGraphReport.Status.FAILED)
        self.assertIn("تعذّر", self.report.error_message)

    def test_successful_extraction_marks_completed_with_stats(self):
        graph_result = {
            "nodes": [{"id": 1}, {"id": 2}],
            "edges": [{"source": 1, "target": 2}],
            "focus_graph": {"nodes": [], "edges": []},
            "top_claims": [{"id": 1}],
            "stats": {"claims": 1, "evidence": 1, "neutral": 0, "edges": 1},
        }
        with patch(FIELD_FILE_PATH, new_callable=PropertyMock, return_value="fake/path.pdf"), \
             patch("ai_service.tasks.extract_text_from_file", return_value=("Some full text.", 1, "pdf")), \
             patch("ai_service.tasks.extract_paper_title", return_value="A Title"), \
             patch("ai_service.tasks.detect_language", return_value="en"), \
             patch("ai_service.tasks.extract_graph", return_value=graph_result):
            result = tasks.analyze_claim_evidence_graph_task(self.report.id)

        self.report.refresh_from_db()
        self.assertEqual(result["status"], ClaimEvidenceGraphReport.Status.COMPLETED)
        self.assertEqual(self.report.status, ClaimEvidenceGraphReport.Status.COMPLETED)
        self.assertEqual(self.report.claims_count, 1)
        self.assertEqual(self.report.evidence_count, 1)
        self.assertEqual(self.report.edges_count, 1)
        self.assertEqual(self.report.paper_title, "A Title")
        self.assertEqual(self.report.detected_language, "en")

    def test_graph_builder_error_marks_failed(self):
        with patch(FIELD_FILE_PATH, new_callable=PropertyMock, return_value="fake/path.pdf"), \
             patch("ai_service.tasks.extract_text_from_file", return_value=("Some full text.", 1, "pdf")), \
             patch("ai_service.tasks.extract_paper_title", return_value="A Title"), \
             patch("ai_service.tasks.detect_language", return_value="en"), \
             patch("ai_service.tasks.extract_graph", return_value={"error": "graph failure"}):
            result = tasks.analyze_claim_evidence_graph_task(self.report.id)

        self.report.refresh_from_db()
        self.assertEqual(result["status"], ClaimEvidenceGraphReport.Status.FAILED)
        self.assertEqual(self.report.error_message, "graph failure")

    def test_unexpected_exception_marks_failed_with_message(self):
        with patch(FIELD_FILE_PATH, new_callable=PropertyMock, return_value="fake/path.pdf"), \
             patch("ai_service.tasks.extract_text_from_file", side_effect=RuntimeError("boom")):
            result = tasks.analyze_claim_evidence_graph_task(self.report.id)

        self.report.refresh_from_db()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"], "boom")
        self.assertEqual(self.report.status, ClaimEvidenceGraphReport.Status.FAILED)
        self.assertEqual(self.report.error_message, "boom")


class IeeeCheckTaskTests(TestCase):
    def setUp(self):
        self.report = IEEECheckReport.objects.create(
            original_filename="paper.pdf",
            full_result={"verify_crossref": True},
        )

    def test_report_not_found_returns_failed_without_raising(self):
        result = tasks.analyze_ieee_check_task(9999)
        self.assertEqual(result, {"status": "failed", "report_id": 9999, "error": "report not found"})

    def test_successful_analysis_populates_report_fields(self):
        raw_result = {
            "paper_title": "A Paper",
            "detected_language": "en",
            "total_pages": 10,
            "citations_in_text": ["a", "b"],
            "total_references": 5,
            "citations_missing_from_references": ["a"],
            "unused_references": [],
            "citation_matching_score": 80.0,
            "format_score": 90.0,
            "crossref_score": 70.0,
            "overall_score": 80.0,
            "status": IEEECheckReport.Status.PASS,
            "summary": "Looks good",
            "crossref_checked": 3,
            "crossref_verified_count": 2,
        }
        with patch(FIELD_FILE_PATH, new_callable=PropertyMock, return_value="fake/path.pdf"), \
             patch("ai_service.tasks.perform_ieee_analysis", return_value=raw_result):
            result = tasks.analyze_ieee_check_task(self.report.id)

        self.report.refresh_from_db()
        self.assertEqual(result["status"], IEEECheckReport.Status.PASS)
        self.assertEqual(self.report.paper_title, "A Paper")
        self.assertEqual(self.report.total_references, 5)
        self.assertEqual(self.report.missing_citations_count, 1)
        self.assertEqual(self.report.crossref_verified, 2)

    def test_analysis_exception_marks_error_status(self):
        with patch(FIELD_FILE_PATH, new_callable=PropertyMock, return_value="fake/path.pdf"), \
             patch("ai_service.tasks.perform_ieee_analysis", side_effect=RuntimeError("parse failed")):
            result = tasks.analyze_ieee_check_task(self.report.id)

        self.report.refresh_from_db()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.report.status, IEEECheckReport.Status.ERROR)
        self.assertIn("parse failed", self.report.summary)


class CheckPaperPlagiarismTaskTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            email="author@example.com", full_name="Author", password="pass1234", specialization="law",
        )
        self.paper = ResearchPaper.objects.create(
            title="Paper", abstract="An abstract long enough for keywording purposes.",
            author=self.author, specialization="law", status=ResearchPaper.Status.SUBMITTED,
        )
        self.other_paper = ResearchPaper.objects.create(
            title="Other paper", abstract="abstract", author=self.author,
            specialization="law", status=ResearchPaper.Status.PUBLISHED,
        )

    def test_paper_not_found_returns_failed_without_raising(self):
        result = tasks.check_paper_plagiarism_task(9999)
        self.assertEqual(result, {"status": "failed", "paper_id": 9999, "error": "paper not found"})

    def _run_with_matches(self, internal_matches, external_matches, ai_keywords=None):
        with patch("ai_service.tasks.AIKeywordExtractor") as mock_extractor_cls, \
             patch("ai_service.tasks.store_chunk_embeddings", return_value=(["chunk"], ["v1"], ["v2"], "en")), \
             patch("ai_service.tasks.find_internal_matches", return_value=internal_matches), \
             patch("ai_service.tasks.run_external_check", return_value=external_matches):
            mock_extractor_cls.return_value.extract_pure_keywords.return_value = ai_keywords or []
            return tasks.check_paper_plagiarism_task(self.paper.id)

    def test_confirmed_match_drives_score_and_no_human_review(self):
        internal_matches = [{
            "confidence_level": "confirmed", "score": 0.9,
            "matched_paper": self.other_paper, "own_snippet": "own", "source_snippet": "src",
        }]
        result = self._run_with_matches(internal_matches, [])

        report = PlagiarismReport.objects.get(paper=self.paper)
        self.assertEqual(report.internal_similarity_score, 90.0)
        self.assertEqual(report.total_similarity_score, 90.0)
        self.assertFalse(report.requires_human_review)
        self.assertEqual(PlagiarismSource.objects.filter(report=report).count(), 1)
        self.assertEqual(result["ai_check_ok"], True)

    def test_only_suspected_matches_require_human_review_and_zero_score(self):
        internal_matches = [{
            "confidence_level": "suspected", "score": 0.4,
            "matched_paper": self.other_paper, "own_snippet": "own", "source_snippet": "src",
        }]
        self._run_with_matches(internal_matches, [])

        report = PlagiarismReport.objects.get(paper=self.paper)
        self.assertEqual(report.internal_similarity_score, 0.0)
        self.assertEqual(report.total_similarity_score, 0.0)
        self.assertTrue(report.requires_human_review)

    def test_confirmed_and_suspected_together_does_not_require_review(self):
        internal_matches = [
            {"confidence_level": "confirmed", "score": 0.8, "matched_paper": self.other_paper,
             "own_snippet": "own", "source_snippet": "src"},
            {"confidence_level": "suspected", "score": 0.35, "matched_paper": self.other_paper,
             "own_snippet": "own2", "source_snippet": "src2"},
        ]
        self._run_with_matches(internal_matches, [])

        report = PlagiarismReport.objects.get(paper=self.paper)
        self.assertFalse(report.requires_human_review)
        self.assertEqual(report.internal_similarity_score, 80.0)

    def test_total_score_takes_max_of_internal_and_external(self):
        internal_matches = [{"confidence_level": "confirmed", "score": 0.5, "matched_paper": self.other_paper,
                              "own_snippet": "own", "source_snippet": "src"}]
        external_matches = [{"confidence_level": "confirmed", "score": 0.7, "source_url": "http://x",
                              "source_title": "X", "own_snippet": "own", "source_snippet": "src"}]
        self._run_with_matches(internal_matches, external_matches)

        report = PlagiarismReport.objects.get(paper=self.paper)
        self.assertEqual(report.internal_similarity_score, 50.0)
        self.assertEqual(report.external_similarity_score, 70.0)
        self.assertEqual(report.total_similarity_score, 70.0)

    def test_services_unavailable_marks_skipped_and_non_blocking(self):
        with patch("ai_service.tasks.AIKeywordExtractor") as mock_extractor_cls, \
             patch("ai_service.tasks.store_chunk_embeddings", None), \
             patch("ai_service.tasks.find_internal_matches", None), \
             patch("ai_service.tasks.run_external_check", None):
            mock_extractor_cls.return_value.extract_pure_keywords.return_value = []
            result = tasks.check_paper_plagiarism_task(self.paper.id)

        report = PlagiarismReport.objects.get(paper=self.paper)
        self.assertEqual(report.status, PlagiarismReport.Status.SKIPPED)
        self.assertFalse(result["ai_check_ok"])
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.SUBMITTED)

    def test_internal_check_exception_is_non_blocking_and_external_still_runs(self):
        external_matches = [{"confidence_level": "confirmed", "score": 0.65, "source_url": "http://x",
                              "source_title": "X", "own_snippet": "own", "source_snippet": "src"}]
        with patch("ai_service.tasks.AIKeywordExtractor") as mock_extractor_cls, \
             patch("ai_service.tasks.store_chunk_embeddings", side_effect=RuntimeError("embed failed")), \
             patch("ai_service.tasks.find_internal_matches") as mock_find, \
             patch("ai_service.tasks.run_external_check", return_value=external_matches):
            mock_extractor_cls.return_value.extract_pure_keywords.return_value = []
            result = tasks.check_paper_plagiarism_task(self.paper.id)

        mock_find.assert_not_called()
        report = PlagiarismReport.objects.get(paper=self.paper)
        self.assertEqual(report.external_similarity_score, 65.0)
        self.assertFalse(result["ai_check_ok"])

    def test_keyword_extraction_failure_is_non_blocking(self):
        with patch("ai_service.tasks.AIKeywordExtractor") as mock_extractor_cls, \
             patch("ai_service.tasks.store_chunk_embeddings", return_value=(["chunk"], ["v1"], ["v2"], "en")), \
             patch("ai_service.tasks.find_internal_matches", return_value=[]), \
             patch("ai_service.tasks.run_external_check", return_value=[]):
            mock_extractor_cls.return_value.extract_pure_keywords.side_effect = RuntimeError("kw failed")
            result = tasks.check_paper_plagiarism_task(self.paper.id)

        report = PlagiarismReport.objects.get(paper=self.paper)
        self.assertEqual(report.ai_keywords, [])
        self.assertTrue(result["ai_check_ok"])

    def test_previous_report_is_replaced_not_duplicated(self):
        PlagiarismReport.objects.create(paper=self.paper, total_similarity_score=10.0)
        self._run_with_matches([], [])
        self.assertEqual(PlagiarismReport.objects.filter(paper=self.paper).count(), 1)

    def test_paper_status_transitions_to_submitted_after_check(self):
        self.paper.status = ResearchPaper.Status.PENDING
        self.paper.save(update_fields=["status"])
        self._run_with_matches([], [])
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.status, ResearchPaper.Status.SUBMITTED)


class ComputePaperEmbeddingTaskTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            email="author2@example.com", full_name="Author", password="pass1234", specialization="law",
        )
        self.paper = ResearchPaper.objects.create(
            title="Paper", abstract="abstract", author=self.author,
            specialization="law", status=ResearchPaper.Status.SUBMITTED,
        )

    def test_paper_not_found_returns_failed(self):
        result = tasks.compute_paper_embedding_task(9999)
        self.assertEqual(result, {"status": "failed", "paper_id": 9999, "error": "paper not found"})

    def test_embedding_model_unavailable_is_skipped(self):
        with patch("ai_service.tasks.get_embedding_model", None), \
             patch("ai_service.tasks._paper_text", None):
            result = tasks.compute_paper_embedding_task(self.paper.id)
        self.assertEqual(result, {"status": "skipped", "paper_id": self.paper.id})

    def test_successful_embedding_computation_is_stored(self):
        fake_vector = MagicMock()
        fake_vector.tolist.return_value = [0.1, 0.2, 0.3]
        fake_model = MagicMock()
        fake_model.encode.return_value = [fake_vector]

        with patch("ai_service.tasks.get_embedding_model", return_value=fake_model), \
             patch("ai_service.tasks._paper_text", return_value="some text"):
            result = tasks.compute_paper_embedding_task(self.paper.id)

        self.assertEqual(result, {"status": "completed", "paper_id": self.paper.id})
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.embedding.embedding_vector, [0.1, 0.2, 0.3])

    def test_encoding_exception_is_non_blocking(self):
        with patch("ai_service.tasks.get_embedding_model", side_effect=RuntimeError("model load failed")), \
             patch("ai_service.tasks._paper_text", return_value="some text"):
            result = tasks.compute_paper_embedding_task(self.paper.id)
        self.assertEqual(result["status"], "failed")
        self.assertIn("model load failed", result["error"])
