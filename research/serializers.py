from rest_framework import serializers

from research.models import ResearchPaper


class ResearchPaperSerializer(
    serializers.ModelSerializer
):

    class Meta:

        model = ResearchPaper

        fields = "__all__"

        read_only_fields = [
            "publisher",
            "status",
            "submission_date",
            "updated_at",
        ]