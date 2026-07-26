from rest_framework import serializers

from accounts.serializers import UserListSerializer
from researchHistory.models import ResearchHistory

class ResearchHistorySerializer(serializers.ModelSerializer):

    changed_by = UserListSerializer(read_only=True)

    class Meta:
        model = ResearchHistory
        fields = [
            "id",
            "paper",
            "from_status",
            "to_status",
            "changed_by",
            "note",
            "created_at",
        ]
        read_only_fields = fields
