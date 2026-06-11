from django.db import models
from research.models import ResearchPaper
from django.conf import settings
from ai_service.models import IEEECheckReport

class EditorReview(models.Model):

    class Stage(models.TextChoices):
        INITIAL = "INITIAL", "مراجعة أولية"
        FINAL = "FINAL", "مراجعة نهائية"

    class Decision(models.TextChoices):
        SEND_TO_COMMITTEE = "SEND_TO_COMMITTEE"
        REVISION_REQUIRED = "REVISION_REQUIRED"
        REJECT = "REJECT"
        ACCEPT = "ACCEPT"

    paper = models.ForeignKey(
        ResearchPaper,
        on_delete=models.CASCADE,
        related_name="editor_reviews"
    )

    editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={
            "role": "editor"
        }
    )

    stage = models.CharField(
        max_length=10,
        choices=Stage.choices,
        default=Stage.INITIAL
    )

    ieee_report = models.ForeignKey(
        IEEECheckReport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    notes = models.TextField()

    decision = models.CharField(
        max_length=30,
        choices=Decision.choices
    )

    language_review_passed = models.BooleanField(
        null=True,
        blank=True
    )

    citation_check_passed = models.BooleanField(
        null=True,
        blank=True
    )

    publisher_permission_obtained = models.BooleanField(
        null=True,
        blank=True
    )

    reviewed_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-reviewed_at"]
