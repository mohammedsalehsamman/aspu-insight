from rest_framework import serializers
from research.models import ResearchPaper, PlagiarismReport, PlagiarismSource
from committees.models import Committee, CommitteeMember

class PlagiarismSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlagiarismSource
        fields = ['id', 'source_url', 'source_title', 'match_percentage', 'matched_text_snippet']

class PlagiarismReportSerializer(serializers.ModelSerializer):
    sources = PlagiarismSourceSerializer(many=True, read_only=True)

    class Meta:
        model = PlagiarismReport
        fields = ['id', 'total_similarity_score', 'ai_keywords', 'checked_at', 'sources']

class ResearchPaperDetailSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    pdf_file = serializers.FileField(required=False, allow_null=True)
    plagiarism_score = serializers.SerializerMethodField()
    plagiarism_report_id = serializers.SerializerMethodField()
    ai_keywords = serializers.SerializerMethodField()
    assistant_editor_report = serializers.CharField(read_only=True)

    class Meta:
        model = ResearchPaper
        fields = [
            'id', 'title', 'abstract', 'is_paid_open_access', 'pdf_file', 
            'author_name', 'status', 'rejection_reason', 'plagiarism_score', 
            'plagiarism_report_id', 'ai_keywords', 'assistant_editor_report',
            'is_reviewed_by_assistant', 'review_blindness_type'
        ]

    def get_author_name(self, obj):
        request = self.context.get('request')
        user = request.user if request else None

        if user and user.is_authenticated:
            blindness = obj.review_blindness_type
            is_assistant = getattr(user, 'is_assistant_editor', False)
            is_editor = (getattr(user, 'role', '') == 'editor') or Committee.objects.filter(paper=obj, editor=user).exists()
            is_reviewer = CommitteeMember.objects.filter(committee__paper=obj, user=user).exists()

            if user == obj.author or user.is_staff:
                return obj.author.get_full_name() if hasattr(obj.author, 'get_full_name') else str(obj.author)

            if blindness == 'double_blind':
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

    def get_ai_keywords(self, obj):
        try:
            return obj.plagiarism_report.ai_keywords
        except PlagiarismReport.DoesNotExist:
            return []

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get('request')
        user = request.user if request else None

        if user and user.is_authenticated:
            if user == instance.author:
                return representation

            is_assistant = getattr(user, 'is_assistant_editor', False)
            committee = Committee.objects.filter(paper=instance).first()
            is_editor = (getattr(user, 'role', '') == 'editor') or (committee and committee.editor == user)

            if is_assistant:
                return representation
            if is_editor:
                if not instance.is_reviewed_by_assistant:
                    return {}
                if not instance.is_committee_assigned:
                    allowed_fields = ['id', 'title', 'abstract', 'assistant_editor_report', 'plagiarism_score', 'plagiarism_report_id', 'ai_keywords']
                    filtered_rep = {field: representation.get(field) for field in allowed_fields}
                    filtered_rep['pdf_file'] = None
                    filtered_rep['author_name'] = representation.get('author_name')
                    return filtered_rep
                return representation

            member = CommitteeMember.objects.filter(committee__paper=instance, user=user).first()
            if member:
                if not instance.is_reviewed_by_assistant:
                    return {}
                if member.committee.status == 'pending' or member.response == 'pending':
                    allowed_fields = ['id', 'title', 'abstract']
                    filtered_rep = {field: representation[field] for field in allowed_fields if field in representation}
                    filtered_rep['pdf_file'] = None
                    filtered_rep['plagiarism_score'] = None
                    filtered_rep['plagiarism_report_id'] = None
                    filtered_rep['ai_keywords'] = []
                    filtered_rep['assistant_editor_report'] = None
                    return filtered_rep
                return representation

            if user.is_staff:
                return representation

        from configuration.security import can_user_access_pdf
        if not can_user_access_pdf(user, instance):
            representation['pdf_file'] = None
            representation['plagiarism_score'] = None
            representation['plagiarism_report_id'] = None
            representation['ai_keywords'] = []

        return representation

ResearchPaperSerializer = ResearchPaperDetailSerializer
        
        