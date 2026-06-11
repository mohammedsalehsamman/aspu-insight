from rest_framework import serializers

from accounts.models import User
from accounts.serializers import UserListSerializer
from assistantReview.models import AssistantReview


class AssistantReviewSerializer(serializers.ModelSerializer):

    assistant = UserListSerializer(read_only=True)
    suggested_reviewers = UserListSerializer(many=True, read_only=True)

    class Meta:
        model = AssistantReview
        fields = [
            "id",
            "paper",
            "assistant",
            "ieee_report",
            "is_format_compliant",
            "is_complete",
            "policy_notes",
            "suggested_reviewers",
            "recommended_decision",
            "notes",
            "decision",
            "reviewed_at",
            "updated_at",
        ]
        read_only_fields = fields


class AssistantReviewCreateSerializer(serializers.ModelSerializer):

    suggested_reviewers = serializers.PrimaryKeyRelatedField(
        many=True,
        required=False,
        queryset=User.objects.filter(role="reviewer")
    )

    class Meta:
        model = AssistantReview
        fields = [
            "ieee_report",
            "is_format_compliant",
            "is_complete",
            "policy_notes",
            "suggested_reviewers",
            "recommended_decision",
            "notes",
            "decision",
        ]
