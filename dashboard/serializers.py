from rest_framework import serializers

from accounts.serializers import UserListSerializer
from research.models import ResearchPaper
from researchHistory.serializers import ResearchHistorySerializer


class AdminResearchPaperSerializer(serializers.ModelSerializer):

    author = UserListSerializer(read_only=True)
    assigned_editor = UserListSerializer(read_only=True)

    class Meta:
        model = ResearchPaper
        fields = [
            'id', 'title', 'abstract', 'author', 'assigned_editor',
            'status', 'specialization', 'is_paid_open_access',
            'review_blindness_type', 'rejection_reason',
            'is_reviewed_by_assistant', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class AdminResearchPaperDetailSerializer(AdminResearchPaperSerializer):

    history = serializers.SerializerMethodField()

    class Meta(AdminResearchPaperSerializer.Meta):
        fields = AdminResearchPaperSerializer.Meta.fields + ['history']

    def get_history(self, obj):
        history = obj.history.select_related('changed_by').order_by('-created_at')[:10]
        return ResearchHistorySerializer(history, many=True).data


class AssignEditorSerializer(serializers.Serializer):
    editor_id = serializers.IntegerField(allow_null=True, required=True)
