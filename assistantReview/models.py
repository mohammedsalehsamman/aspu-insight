from django.db import models
from research.models import ResearchPaper
from django.conf import settings
from ai_service.models import IEEECheckReport


class AssistantReview(models.Model):

    class Decision(models.TextChoices):
        APPROVE = "APPROVE"
        REJECT = "REJECT"

    class RecommendedDecision(models.TextChoices):
        SEND_TO_COMMITTEE = "SEND_TO_COMMITTEE"
        REVISION_REQUIRED = "REVISION_REQUIRED"
        REJECT = "REJECT"

    paper = models.ForeignKey(
        ResearchPaper,
        on_delete=models.CASCADE,
        related_name="assistant_reviews"
    )

    assistant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={
            "role": "reviewer_assistant"
        }
    )

    ieee_report = models.ForeignKey(
        IEEECheckReport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistant_reviews"
    )

    is_format_compliant = models.BooleanField(
        default=True
    )

    is_complete = models.BooleanField(
        default=True
    )

    policy_notes = models.TextField(
        blank=True,
        default=""
    )

    suggested_reviewers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="suggested_in_assistant_reviews",
        limit_choices_to={
            "role": "reviewer"
        }
    )

    recommended_decision = models.CharField(
        max_length=30,
        choices=RecommendedDecision.choices,
        blank=True
    )

    notes = models.TextField()

    decision = models.CharField(
        max_length=20,
        choices=Decision.choices
    )

    reviewed_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-reviewed_at"]
