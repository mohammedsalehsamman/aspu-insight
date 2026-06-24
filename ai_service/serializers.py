from rest_framework import serializers
from .models import IEEECheckReport, ClaimEvidenceGraphReport


class IEEECheckReportListSerializer(serializers.ModelSerializer):

    status_display = serializers.SerializerMethodField()

    class Meta:
        model = IEEECheckReport
        fields = [
            'id',
            'original_filename',
            'paper_title',
            'detected_language',
            'total_pages',
            'total_references',
            'total_citations_in_text',
            'missing_citations_count',
            'unused_references_count',
            'overall_score',
            'citation_matching_score',
            'format_score',
            'crossref_score',
            'status',
            'status_display',
            'processing_time_seconds',
            'created_at',
        ]

    def get_status_display(self, obj) -> str:
        return obj.status_display_ar


class IEEECheckReportSerializer(serializers.ModelSerializer):
    status_display   = serializers.SerializerMethodField()
    recommendations  = serializers.SerializerMethodField()
    references_list  = serializers.SerializerMethodField()

    class Meta:
        model = IEEECheckReport
        fields = [
            'id',
            'original_filename',
            'paper_title',
            'detected_language',
            'total_pages',
            'total_citations_in_text',
            'total_references',
            'missing_citations_count',
            'unused_references_count',
            'overall_score',
            'citation_matching_score',
            'format_score',
            'crossref_score',
            'crossref_checked',
            'crossref_verified',
            'status',
            'status_display',
            'summary',
            'recommendations',
            'references_list',
            'full_result',
            'processing_time_seconds',
            'created_at',
        ]

    def get_status_display(self, obj) -> str:
        return obj.status_display_ar

    def get_recommendations(self, obj) -> list:
        return obj.recommendations

    def get_references_list(self, obj) -> list:
        return obj.references_list


class ClaimEvidenceGraphReportListSerializer(serializers.ModelSerializer):

    status_display = serializers.SerializerMethodField()

    class Meta:
        model = ClaimEvidenceGraphReport
        fields = [
            'id',
            'original_filename',
            'paper_title',
            'detected_language',
            'status',
            'status_display',
            'claims_count',
            'evidence_count',
            'neutral_count',
            'edges_count',
            'similarity_threshold',
            'top_claims_count',
            'processing_time_seconds',
            'created_at',
        ]

    def get_status_display(self, obj) -> str:
        return obj.status_display_ar


class ClaimEvidenceGraphReportSerializer(serializers.ModelSerializer):

    status_display = serializers.SerializerMethodField()
    focus_graph     = serializers.SerializerMethodField()
    top_claims      = serializers.SerializerMethodField()

    class Meta:
        model = ClaimEvidenceGraphReport
        fields = [
            'id',
            'original_filename',
            'paper_title',
            'detected_language',
            'status',
            'status_display',
            'graph_data',
            'focus_graph',
            'top_claims',
            'claims_count',
            'evidence_count',
            'neutral_count',
            'edges_count',
            'similarity_threshold',
            'top_claims_count',
            'source_excerpt',
            'summary',
            'error_message',
            'processing_time_seconds',
            'created_at',
        ]

    def get_status_display(self, obj) -> str:
        return obj.status_display_ar

    def get_focus_graph(self, obj) -> dict:
        return obj.focus_graph

    def get_top_claims(self, obj) -> list:
        return obj.top_claims
