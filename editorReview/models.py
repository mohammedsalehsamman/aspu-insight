from django.db import models
from research.models import ResearchPaper
from django.conf import settings
from ai_service.models import IEEECheckReport

class EditorReview(models.Model):

    class Decision(models.TextChoices):
        SEND_TO_COMMITTEE = "SEND_TO_COMMITTEE"
        REVISION_REQUIRED = "REVISION_REQUIRED"
        REJECT = "REJECT"

    paper = models.OneToOneField(
        ResearchPaper,
        on_delete=models.CASCADE,
        related_name="editor_review"
    )

    editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={
            "role": "editor"
        }
    )

    ieee_report = models.ForeignKey(
        IEEECheckReport,
        on_delete=models.SET_NULL,
        null=True
    )

    notes = models.TextField()

    decision = models.CharField(
        max_length=30,
        choices=Decision.choices
    )

    reviewed_at = models.DateTimeField(
        auto_now_add=True
    )