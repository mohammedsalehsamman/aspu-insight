from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, override_settings

from ai_service.plagiarism.services import external_sources


@override_settings(
    SEMANTIC_SCHOLAR_API_KEY='',
    CORE_API_KEY='',
    VALUESERP_API_KEY='',
    PLAGIARISM_EXTERNAL_SIMILARITY_THRESHOLD=0.6,
    PLAGIARISM_SUSPECTED_EXTERNAL_THRESHOLD=0.3,
)
class SearchSemanticScholarTests(SimpleTestCase):
    def test_empty_keywords_short_circuits_without_calling_requests(self):
        with patch("requests.get") as mock_get:
            result = external_sources.search_semantic_scholar([], ["chunk"], [[0.1]])
        self.assertEqual(result, [])
        mock_get.assert_not_called()

    def test_empty_chunks_short_circuits_without_calling_requests(self):
        with patch("requests.get") as mock_get:
            result = external_sources.search_semantic_scholar(["keyword"], [], [])
        self.assertEqual(result, [])
        mock_get.assert_not_called()

    def _fake_response(self, papers):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"data": papers}
        return resp

    def test_confirmed_when_score_at_or_above_threshold(self):
        paper = {"title": "Paper A", "url": "http://a", "abstract": "text", "openAccessPdf": None}
        with patch("requests.get", return_value=self._fake_response([paper])), \
             patch.object(external_sources, "_best_match_against_chunks", return_value=(0.9, "own", "src")):
            result = external_sources.search_semantic_scholar(["kw"], ["chunk"], [[0.1]])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["confidence_level"], "confirmed")
        self.assertEqual(result[0]["score"], 0.9)

    def test_suspected_when_score_between_thresholds(self):
        paper = {"title": "Paper A", "url": "http://a", "abstract": "text", "openAccessPdf": None}
        with patch("requests.get", return_value=self._fake_response([paper])), \
             patch.object(external_sources, "_best_match_against_chunks", return_value=(0.4, "own", "src")):
            result = external_sources.search_semantic_scholar(["kw"], ["chunk"], [[0.1]])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["confidence_level"], "suspected")

    def test_excluded_when_score_below_suspected_threshold(self):
        paper = {"title": "Paper A", "url": "http://a", "abstract": "text", "openAccessPdf": None}
        with patch("requests.get", return_value=self._fake_response([paper])), \
             patch.object(external_sources, "_best_match_against_chunks", return_value=(0.1, "own", "src")):
            result = external_sources.search_semantic_scholar(["kw"], ["chunk"], [[0.1]])
        self.assertEqual(result, [])

    def test_429_retries_then_succeeds(self):
        rate_limited = MagicMock()
        rate_limited.status_code = 429
        ok_response = self._fake_response([])
        with patch("requests.get", side_effect=[rate_limited, ok_response]), \
             patch("time.sleep"):
            result = external_sources.search_semantic_scholar(["kw"], ["chunk"], [[0.1]], max_retries=3)
        self.assertEqual(result, [])

    def test_429_exhausts_retries_and_gives_up(self):
        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.raise_for_status.side_effect = requests.exceptions.HTTPError("429")
        with patch("requests.get", return_value=rate_limited) as mock_get, \
             patch("time.sleep"):
            result = external_sources.search_semantic_scholar(["kw"], ["chunk"], [[0.1]], max_retries=3)
        self.assertEqual(result, [])
        self.assertEqual(mock_get.call_count, 3)

    def test_request_exception_is_non_blocking(self):
        with patch("requests.get", side_effect=requests.exceptions.RequestException("boom")):
            result = external_sources.search_semantic_scholar(["kw"], ["chunk"], [[0.1]])
        self.assertEqual(result, [])


@override_settings(
    CORE_API_KEY='core-key',
    PLAGIARISM_EXTERNAL_SIMILARITY_THRESHOLD=0.6,
    PLAGIARISM_SUSPECTED_EXTERNAL_THRESHOLD=0.3,
)
class SearchCoreTests(SimpleTestCase):
    def _fake_response(self, works):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"results": works}
        return resp

    def test_missing_api_key_short_circuits(self):
        with override_settings(CORE_API_KEY=''), patch("requests.get") as mock_get:
            result = external_sources.search_core(["kw"], ["chunk"], [[0.1]])
        self.assertEqual(result, [])
        mock_get.assert_not_called()

    def test_empty_keywords_short_circuits(self):
        with patch("requests.get") as mock_get:
            result = external_sources.search_core([], ["chunk"], [[0.1]])
        self.assertEqual(result, [])
        mock_get.assert_not_called()

    def test_empty_chunks_short_circuits(self):
        with patch("requests.get") as mock_get:
            result = external_sources.search_core(["kw"], [], [])
        self.assertEqual(result, [])
        mock_get.assert_not_called()

    def test_confirmed_classification(self):
        work = {"title": "Work A", "downloadUrl": "http://a", "fullText": "text"}
        with patch("requests.get", return_value=self._fake_response([work])), \
             patch.object(external_sources, "_best_match_against_chunks", return_value=(0.75, "own", "src")):
            result = external_sources.search_core(["kw"], ["chunk"], [[0.1]])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["confidence_level"], "confirmed")

    def test_suspected_classification(self):
        work = {"title": "Work A", "downloadUrl": "http://a", "fullText": "text"}
        with patch("requests.get", return_value=self._fake_response([work])), \
             patch.object(external_sources, "_best_match_against_chunks", return_value=(0.35, "own", "src")):
            result = external_sources.search_core(["kw"], ["chunk"], [[0.1]])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["confidence_level"], "suspected")

    def test_request_exception_is_non_blocking(self):
        with patch("requests.get", side_effect=requests.exceptions.RequestException("boom")):
            result = external_sources.search_core(["kw"], ["chunk"], [[0.1]])
        self.assertEqual(result, [])


@override_settings(
    VALUESERP_API_KEY='vs-key',
    PLAGIARISM_EXTERNAL_SIMILARITY_THRESHOLD=0.6,
    PLAGIARISM_SUSPECTED_EXTERNAL_THRESHOLD=0.3,
)
class SearchValueSerpTests(SimpleTestCase):
    def _fake_response(self, organic_results):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"organic_results": organic_results}
        return resp

    def test_missing_api_key_short_circuits(self):
        with override_settings(VALUESERP_API_KEY=''), patch("requests.get") as mock_get:
            result = external_sources.search_valueserp(["chunk"], [[0.1]])
        self.assertEqual(result, [])
        mock_get.assert_not_called()

    def test_empty_chunks_short_circuits(self):
        with patch("requests.get") as mock_get:
            result = external_sources.search_valueserp([], [])
        self.assertEqual(result, [])
        mock_get.assert_not_called()

    def test_confirmed_and_suspected_classification(self):
        organic = [
            {"title": "Confirmed Source", "link": "http://confirmed", "snippet": "matched text"},
            {"title": "Suspected Source", "link": "http://suspected", "snippet": "similar text"},
            {"title": "No snippet", "link": "http://empty", "snippet": ""},
        ]
        fake_model = MagicMock()
        fake_model.encode.return_value = [[0.5]]
        with patch("requests.get", return_value=self._fake_response(organic)), \
             patch.object(external_sources, "_embedding_model", return_value=fake_model), \
             patch.object(external_sources, "cosine_similarity", side_effect=[[[0.9]], [[0.4]]]), \
             patch("time.sleep"):
            result = external_sources.search_valueserp(["chunk"], [[0.1]])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["confidence_level"], "confirmed")
        self.assertEqual(result[1]["confidence_level"], "suspected")

    def test_request_exception_for_one_chunk_is_non_blocking(self):
        with patch("requests.get", side_effect=requests.exceptions.RequestException("boom")), \
             patch("time.sleep"):
            result = external_sources.search_valueserp(["chunk"], [[0.1]])
        self.assertEqual(result, [])


class RunExternalCheckTests(SimpleTestCase):
    def test_none_vectors_returns_empty(self):
        result = external_sources.run_external_check(["chunk"], None, ["kw"])
        self.assertEqual(result, [])

    def test_empty_chunks_returns_empty(self):
        result = external_sources.run_external_check([], [[0.1]], ["kw"])
        self.assertEqual(result, [])

    def test_aggregates_all_three_sources(self):
        with patch.object(external_sources, "search_semantic_scholar", return_value=[{"source": "ss"}]) as mock_ss, \
             patch.object(external_sources, "search_core", return_value=[{"source": "core"}]) as mock_core, \
             patch.object(external_sources, "search_valueserp", return_value=[{"source": "vs"}]) as mock_vs:
            result = external_sources.run_external_check(["chunk"], [[0.1]], ["kw"])
        self.assertEqual(
            result,
            [{"source": "ss"}, {"source": "core"}, {"source": "vs"}],
        )
        mock_ss.assert_called_once()
        mock_core.assert_called_once()
        mock_vs.assert_called_once()
