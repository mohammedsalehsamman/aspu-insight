from django.test import TestCase

from ai_service.models import ClaimEvidenceGraphReport, IEEECheckReport
from ai_service.serializers import (
    ClaimEvidenceGraphReportListSerializer,
    ClaimEvidenceGraphReportSerializer,
    IEEECheckReportListSerializer,
    IEEECheckReportSerializer,
)


class IEEECheckReportSerializerTests(TestCase):
    def setUp(self):
        self.report = IEEECheckReport.objects.create(
            original_filename="paper.pdf",
            status=IEEECheckReport.Status.PASS,
            overall_score=88.5,
            full_result={
                "recommendations": ["Fix citation 3", "Add missing reference"],
                "references": [{"title": "Ref 1"}],
            },
        )

    def test_status_display_maps_known_status(self):
        data = IEEECheckReportSerializer(self.report).data
        self.assertEqual(data["status_display"], " مقبول")

    def test_status_display_falls_back_to_raw_status_for_unknown(self):
        self.report.status = "unknown_status"
        self.report.save(update_fields=["status"])
        data = IEEECheckReportListSerializer(self.report).data
        self.assertEqual(data["status_display"], "unknown_status")

    def test_recommendations_pulled_from_full_result(self):
        data = IEEECheckReportSerializer(self.report).data
        self.assertEqual(data["recommendations"], ["Fix citation 3", "Add missing reference"])

    def test_recommendations_default_to_empty_list_when_absent(self):
        self.report.full_result = {}
        self.report.save(update_fields=["full_result"])
        data = IEEECheckReportSerializer(self.report).data
        self.assertEqual(data["recommendations"], [])

    def test_references_list_pulled_from_full_result(self):
        data = IEEECheckReportSerializer(self.report).data
        self.assertEqual(data["references_list"], [{"title": "Ref 1"}])

    def test_list_serializer_excludes_detail_only_fields(self):
        data = IEEECheckReportListSerializer(self.report).data
        self.assertNotIn("recommendations", data)
        self.assertNotIn("references_list", data)
        self.assertNotIn("full_result", data)
        self.assertIn("overall_score", data)


class ClaimEvidenceGraphReportSerializerTests(TestCase):
    def setUp(self):
        self.report = ClaimEvidenceGraphReport.objects.create(
            original_filename="paper.pdf",
            status=ClaimEvidenceGraphReport.Status.COMPLETED,
            graph_data={
                "nodes": [{"id": 1}],
                "edges": [{"source": 1, "target": 2}],
                "focus_graph": {"nodes": [{"id": 1}], "edges": []},
                "top_claims": [{"id": 1, "text": "claim"}],
            },
        )

    def test_status_display_maps_known_status(self):
        data = ClaimEvidenceGraphReportSerializer(self.report).data
        self.assertEqual(data["status_display"], "مكتمل")

    def test_status_display_falls_back_for_unknown_status(self):
        self.report.status = "mystery"
        self.report.save(update_fields=["status"])
        data = ClaimEvidenceGraphReportListSerializer(self.report).data
        self.assertEqual(data["status_display"], "mystery")

    def test_focus_graph_pulled_from_graph_data(self):
        data = ClaimEvidenceGraphReportSerializer(self.report).data
        self.assertEqual(data["focus_graph"], {"nodes": [{"id": 1}], "edges": []})

    def test_focus_graph_defaults_when_missing(self):
        self.report.graph_data = {}
        self.report.save(update_fields=["graph_data"])
        data = ClaimEvidenceGraphReportSerializer(self.report).data
        self.assertEqual(data["focus_graph"], {"nodes": [], "edges": []})

    def test_top_claims_pulled_from_graph_data(self):
        data = ClaimEvidenceGraphReportSerializer(self.report).data
        self.assertEqual(data["top_claims"], [{"id": 1, "text": "claim"}])

    def test_top_claims_default_to_empty_list_when_missing(self):
        self.report.graph_data = {}
        self.report.save(update_fields=["graph_data"])
        data = ClaimEvidenceGraphReportSerializer(self.report).data
        self.assertEqual(data["top_claims"], [])

    def test_list_serializer_excludes_detail_only_fields(self):
        data = ClaimEvidenceGraphReportListSerializer(self.report).data
        self.assertNotIn("graph_data", data)
        self.assertNotIn("focus_graph", data)
        self.assertNotIn("top_claims", data)
        self.assertIn("claims_count", data)
