from django.core.validators import FileExtensionValidator
from rest_framework import serializers
from research.models import ResearchPaper, PlagiarismReport, PlagiarismSource, MetadataQualityReport
from research.validators import validate_file_size, validate_pdf_content
from committees.models import Committee, CommitteeMember

class PlagiarismSourceSerializer(serializers.ModelSerializer):
    matched_paper_title = serializers.CharField(source='matched_paper.title', read_only=True, default=None)

    class Meta:
        model = PlagiarismSource
        fields = [
            'id', 'source_type', 'confidence_level', 'matched_paper', 'matched_paper_title',
            'source_url', 'source_title', 'match_percentage',
            'own_text_snippet', 'source_text_snippet'
        ]

class PlagiarismReportSerializer(serializers.ModelSerializer):
    sources = PlagiarismSourceSerializer(many=True, read_only=True)

    class Meta:
        model = PlagiarismReport
        fields = [
            'id', 'status', 'total_similarity_score', 'internal_similarity_score',
            'external_similarity_score', 'requires_human_review', 'ai_keywords', 'checked_at', 'sources'
        ]

class MetadataQualityReportSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='status_display_ar', read_only=True)

    class Meta:
        model = MetadataQualityReport
        fields = [
            'id', 'overall_score', 'sub_scores', 'breakdown', 'recommendations',
            'status', 'status_display', 'created_at', 'updated_at'
        ]

class ResearchPaperDetailSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    pdf_file = serializers.FileField(
        required=False, allow_null=True,
        validators=[validate_file_size, FileExtensionValidator(allowed_extensions=['pdf']), validate_pdf_content]
    )
    plagiarism_score = serializers.SerializerMethodField()
    plagiarism_report_id = serializers.SerializerMethodField()
    plagiarism_status = serializers.SerializerMethodField()
    ai_keywords = serializers.SerializerMethodField()
    metadata_quality_score = serializers.SerializerMethodField()
    assistant_editor_report = serializers.CharField(read_only=True)

    class Meta:
        model = ResearchPaper
        fields = [
            'id', 'title', 'abstract', 'is_paid_open_access', 'pdf_file',
            'author_name', 'status', 'rejection_reason', 'plagiarism_score', 'specialization',
            'plagiarism_report_id', 'plagiarism_status', 'ai_keywords', 'metadata_quality_score',
            'assistant_editor_report', 'is_reviewed_by_assistant', 'review_blindness_type'
        ]
        read_only_fields = ['review_blindness_type']

    def get_author_name(self, obj):
        request = self.context.get('request')
        user = request.user if request else None

        if user and user.is_authenticated:
            blindness = obj.review_blindness_type
            
            is_assistant = getattr(user, 'is_assistant_editor', False) or getattr(user, 'role', '') in ['assistant_editor', 'assistant', 'assistant_editor']
            is_editor = (getattr(user, 'role', '') == 'editor') or Committee.objects.filter(paper=obj, editor=user).exists()
            is_reviewer = CommitteeMember.objects.filter(committee__paper=obj, user=user).exists()

            if user == obj.author or user.is_staff:
                return obj.author.get_full_name() if hasattr(obj.author, 'get_full_name') else str(obj.author)

            if blindness == 'double_blind':
                if is_assistant or is_editor:
                    return obj.author.get_full_name() if hasattr(obj.author, 'get_full_name') else str(obj.author)
                return "Anonymous Author (Hidden for Double Blind Review)"

            if blindness == 'single_blind':
                if is_assistant or is_editor:
                    return obj.author.get_full_name() if hasattr(obj.author, 'get_full_name') else str(obj.author)
                if is_reviewer:
                    return "Anonymous Author (Hidden for Single Blind Review)"

            if blindness == 'open_review':
                return obj.author.get_full_name() if hasattr(obj.author, 'get_full_name') else str(obj.author)

        return "Anonymous Author (Hidden for Blind Review)"

    def get_plagiarism_score(self, obj):
        try:
            return obj.plagiarism_report.total_similarity_score
        except PlagiarismReport.DoesNotExist:
            return None

    def get_plagiarism_report_id(self, obj):
        try:
            return obj.plagiarism_report.id
        except PlagiarismReport.DoesNotExist:
            return None

    def get_plagiarism_status(self, obj):
        try:
            return obj.plagiarism_report.status
        except PlagiarismReport.DoesNotExist:
            return 'pending'

    def get_ai_keywords(self, obj):
        try:
            return obj.plagiarism_report.ai_keywords
        except PlagiarismReport.DoesNotExist:
            return []

    def get_metadata_quality_score(self, obj):
        try:
            return obj.metadata_quality_report.overall_score
        except MetadataQualityReport.DoesNotExist:
            return None

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get('request')
        user = request.user if request else None

        if user and user.is_authenticated:

            if user == instance.author or user.is_staff:
                return representation
            is_assistant = getattr(user, 'is_assistant_editor', False) or getattr(user, 'role', '') in ['assistant_editor', 'assistant', 'assistant_editor']

            committee = instance.committee if hasattr(instance, 'committee') else None
            is_editor = (getattr(user, 'role', '') == 'editor') or (committee and committee.editor == user)

            if is_assistant:
                return representation

            if not instance.is_reviewed_by_assistant:
                return {}

            if is_editor:

                if not committee or committee.status == 'pending':
                    allowed_fields = ['id', 'title', 'abstract', 'assistant_editor_report']
                    filtered_rep = {field: representation.get(field) for field in allowed_fields}
                    filtered_rep['pdf_file'] = None
                    filtered_rep['author_name'] = representation.get('author_name')
                    filtered_rep['plagiarism_score'] = None
                    filtered_rep['plagiarism_report_id'] = None
                    filtered_rep['ai_keywords'] = []
                    filtered_rep['metadata_quality_score'] = None
                    return filtered_rep
                return representation

            member = CommitteeMember.objects.filter(committee__paper=instance, user=user).first()
            if member:

                if member.committee.status == 'pending' or member.response == 'pending':
                    allowed_fields = ['id', 'title', 'abstract', 'assistant_editor_report']
                    filtered_rep = {field: representation.get(field) for field in allowed_fields if field in representation}
                    filtered_rep['pdf_file'] = None
                    filtered_rep['plagiarism_score'] = None
                    filtered_rep['plagiarism_report_id'] = None
                    filtered_rep['ai_keywords'] = []
                    filtered_rep['metadata_quality_score'] = None
                    return filtered_rep
                return representation

        from configuration.security import can_user_access_pdf
        if not can_user_access_pdf(user, instance):
            representation['pdf_file'] = None
            representation['plagiarism_score'] = None
            representation['plagiarism_report_id'] = None
            representation['ai_keywords'] = []
            representation['metadata_quality_score'] = None

        return representation

ResearchPaperSerializer = ResearchPaperDetailSerializer