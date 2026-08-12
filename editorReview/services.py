from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError, NotFound

from research.models import ResearchPaper
from researchHistory.models import ResearchHistory
from editorReview.models import EditorReview
from notifications.models import Notification
from notifications.services import NotificationService

User = get_user_model()

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
    def _check_assigned_editor(paper, editor):
        from research.service import ResearchPaperService
        return ResearchPaperService.check_assigned_editor(paper, editor)

    @staticmethod
    def _apply_transition(paper, editor, review, note):

        from_status = paper.status

        paper.status = STATUS_BY_DECISION[review.decision]

        if paper.status in (ResearchPaper.Status.REJECTED, ResearchPaper.Status.REVISION_REQUIRED):
            paper.rejection_reason = note
        else:
            paper.rejection_reason = ""

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

        EditorReviewService._check_assigned_editor(paper, editor)

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

        EditorReviewService._check_assigned_editor(paper, editor)

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

        EditorReviewService._check_assigned_editor(paper, editor)

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

    @staticmethod
    def assign_assistant_editor(paper, editor, assistant_editor_id):

        EditorReviewService._check_assigned_editor(paper, editor)

        if assistant_editor_id is None:
            paper.assigned_assistant_editor = None
            paper.save(update_fields=["assigned_assistant_editor"])
            return paper

        try:
            assistant_editor = User.objects.get(
                user_id=assistant_editor_id, role="assistant_editor"
            )
        except User.DoesNotExist:
            raise NotFound(
                "المستخدم المطلوب غير موجود أو ليس مساعد محرر."
            )

        paper.assigned_assistant_editor = assistant_editor
        paper.save(update_fields=["assigned_assistant_editor"])

        NotificationService.create_notification(
            recipient=assistant_editor,
            notification_type=Notification.NotificationType.ASSISTANT_EDITOR_ASSIGNED,
            actor=editor,
            target=paper,
            target_repr=paper.title,
            context={
                "paper_title": paper.title,
                "fallback_title": "تعيينك مساعد محرر لبحث",
                "fallback_body": f"تم تعيينك مساعد محرر مسؤولاً عن مراجعة البحث: {paper.title}",
            },
        )

        return paper
