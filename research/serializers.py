from rest_framework import serializers
from research.models import ResearchPaper
from committees.models import Committee, CommitteeMember

class ResearchPaperDetailSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    pdf_file = serializers.FileField(required=False, allow_null=True)

    class Meta:
        model = ResearchPaper
        fields = ['id', 'title', 'abstract', 'is_paid_open_access', 'pdf_file', 'author_name', 'status', 'rejection_reason']

    def get_author_name(self, obj):
        request = self.context.get('request')
        user = request.user if request else None

        if user and user.is_authenticated:
            if user == obj.author or user.is_staff or getattr(user, 'role', '') == 'editor':
                return obj.author.get_full_name() if hasattr(obj.author, 'get_full_name') else str(obj.author)
        
        return "Anonymous Author (Hidden for Blind Review)"

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get('request')
        user = request.user if request else None

        if user and user.is_authenticated:
            committee = Committee.objects.filter(paper=instance).first()
            is_editor = (getattr(user, 'role', '') == 'editor') or (committee and committee.editor == user)

            if is_editor:
                if not committee or committee.status == 'pending':
                    allowed_fields = ['id', 'title', 'abstract']
                    filtered_rep = {field: representation[field] for field in allowed_fields if field in representation}
                    filtered_rep['pdf_file'] = None
                    return filtered_rep

            member = CommitteeMember.objects.filter(committee__paper=instance, user=user).first()
            if member:
                if member.committee.status == 'pending' or member.response == 'pending':
                    allowed_fields = ['id', 'title', 'abstract']
                    filtered_rep = {field: representation[field] for field in allowed_fields if field in representation}
                    filtered_rep['pdf_file'] = None
                    return filtered_rep

            if user == instance.author or user.is_staff or getattr(user, 'role', '') == 'editor':
                return representation

        from configuration.security import can_user_access_pdf
        if not can_user_access_pdf(user, instance):
            representation['pdf_file'] = None

        return representation

ResearchPaperSerializer = ResearchPaperDetailSerializer