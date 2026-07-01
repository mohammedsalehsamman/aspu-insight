from rest_framework.exceptions import ValidationError

from research.models import ResearchPaper
from researchHistory.models import ResearchHistory
from editorReview.models import EditorReview


INITIAL_DECISIONS = {
    EditorReview.Decision.SEND_TO_COMMITTEE,
    EditorReview.Decision.REVISION_REQUIRED,
    EditorReview.Decision.REJECT,
}

FINAL_DECISIONS = {
    EditorReview.Decision.ACCEPT,
    EditorReview.Decision.REVISION_REQUIRED,
    EditorReview.Decision.REJECT,
}

STATUS_BY_DECISION = {
    EditorReview.Decision.SEND_TO_COMMITTEE: ResearchPaper.Status.COMMITTEE_REVIEW,
    EditorReview.Decision.REVISION_REQUIRED: ResearchPaper.Status.REVISION_REQUIRED,
    EditorReview.Decision.REJECT:            ResearchPaper.Status.REJECTED,
    EditorReview.Decision.ACCEPT:            ResearchPaper.Status.ACCEPTED,
}


class EditorReviewService:

    @staticmethod
    def _apply_transition(paper, editor, review, note):

        from_status = paper.status

        paper.status = STATUS_BY_DECISION[review.decision]
        paper.save()

        ResearchHistory.objects.create(
            paper=paper,
            from_status=from_status,
            to_status=paper.status,
            changed_by=editor,
            note=note
        )

    @staticmethod
    def create_initial_review(paper, editor, validated_data):

        if paper.status != ResearchPaper.Status.EDITOR_REVIEW:
            raise ValidationError(
                "Paper is not awaiting editor review."
            )

        decision = validated_data["decision"]

        if decision not in INITIAL_DECISIONS:
            raise ValidationError(
                "Invalid decision for the initial editor review."
            )

        review = EditorReview.objects.create(
            paper=paper,
            editor=editor,
            stage=EditorReview.Stage.INITIAL,
            **validated_data
        )

        EditorReviewService._apply_transition(
            paper,
            editor,
            review,
            validated_data.get("notes", "")
        )

        return review

    @staticmethod
    def create_final_review(paper, editor, validated_data):

        if paper.status != ResearchPaper.Status.COMMITTEE_REVIEW:
            raise ValidationError(
                "Paper is not awaiting the editor's final review."
            )

        decision = validated_data["decision"]

        if decision not in FINAL_DECISIONS:
            raise ValidationError(
                "Invalid decision for the final editor review."
            )

        if decision == EditorReview.Decision.ACCEPT:

            checklist = (
                validated_data.get("language_review_passed"),
                validated_data.get("citation_check_passed"),
                validated_data.get("publisher_permission_obtained"),
            )

            if not all(checklist):
                raise ValidationError(
                    "Language review, citation check and publisher "
                    "permission must all be confirmed before acceptance."
                )

        review = EditorReview.objects.create(
            paper=paper,
            editor=editor,
            stage=EditorReview.Stage.FINAL,
            **validated_data
        )

        EditorReviewService._apply_transition(
            paper,
            editor,
            review,
            validated_data.get("notes", "")
        )

        return review

    @staticmethod
    def publish_paper(paper, editor):

        if paper.status != ResearchPaper.Status.ACCEPTED:
            raise ValidationError(
                "Only accepted papers can be published."
            )

        from_status = paper.status

        paper.status = ResearchPaper.Status.PUBLISHED
        paper.save()

        ResearchHistory.objects.create(
            paper=paper,
            from_status=from_status,
            to_status=paper.status,
            changed_by=editor,
            note="Published"
        )

        return paper
