from rest_framework import serializers

from accounts.serializers import UserListSerializer
from editorReview.models import EditorReview


class EditorReviewSerializer(serializers.ModelSerializer):

    editor = UserListSerializer(read_only=True)

    class Meta:
        model = EditorReview
        fields = [
            "id",
            "paper",
            "editor",
            "stage",
            "ieee_report",
            "notes",
            "decision",
            "language_review_passed",
            "citation_check_passed",
            "publisher_permission_obtained",
            "reviewed_at",
            "updated_at",
        ]
        read_only_fields = fields


class EditorInitialReviewSerializer(serializers.ModelSerializer):

    class Meta:
        model = EditorReview
        fields = [
            "ieee_report",
            "notes",
            "decision",
        ]

    def validate_decision(self, value):

        allowed = {
            EditorReview.Decision.SEND_TO_COMMITTEE,
            EditorReview.Decision.REVISION_REQUIRED,
            EditorReview.Decision.REJECT,
        }

        if value not in allowed:
            raise serializers.ValidationError(
                "Invalid decision for the initial editor review."
            )

        return value


class EditorFinalReviewSerializer(serializers.ModelSerializer):

    class Meta:
        model = EditorReview
        fields = [
            "notes",
            "decision",
            "language_review_passed",
            "citation_check_passed",
            "publisher_permission_obtained",
        ]

    def validate_decision(self, value):

        allowed = {
            EditorReview.Decision.ACCEPT,
            EditorReview.Decision.REVISION_REQUIRED,
            EditorReview.Decision.REJECT,
        }

        if value not in allowed:
            raise serializers.ValidationError(
                "Invalid decision for the final editor review."
            )

        return value

    def validate(self, attrs):

        if attrs.get("decision") == EditorReview.Decision.ACCEPT:

            checklist = (
                attrs.get("language_review_passed"),
                attrs.get("citation_check_passed"),
                attrs.get("publisher_permission_obtained"),
            )

            if not all(checklist):
                raise serializers.ValidationError(
                    "Language review, citation check and publisher "
                    "permission must all be confirmed before acceptance."
                )

        return attrs
