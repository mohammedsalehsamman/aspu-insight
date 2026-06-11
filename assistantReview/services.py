from rest_framework.exceptions import ValidationError

from research.models import ResearchPaper
from researchHistory.models import ResearchHistory
from assistantReview.models import AssistantReview


class AssistantReviewService:

    @staticmethod
    def create_review(paper, assistant, validated_data):

        if paper.status != ResearchPaper.Status.SUBMITTED:
            raise ValidationError(
                "Paper is not awaiting assistant review."
            )

        suggested_reviewers = validated_data.pop(
            "suggested_reviewers",
            []
        )

        decision = validated_data["decision"]

        review = AssistantReview.objects.create(
            paper=paper,
            assistant=assistant,
            **validated_data
        )

        review.suggested_reviewers.set(suggested_reviewers)

        from_status = paper.status

        if decision == AssistantReview.Decision.APPROVE:
            paper.status = ResearchPaper.Status.EDITOR_REVIEW
        else:
            paper.status = ResearchPaper.Status.REVISION_REQUIRED

        paper.save()

        ResearchHistory.objects.create(
            paper=paper,
            from_status=from_status,
            to_status=paper.status,
            changed_by=assistant,
            note=validated_data.get("notes", "")
        )

        return review
