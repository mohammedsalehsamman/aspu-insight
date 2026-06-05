from django.db import models
from research.models import ResearchPaper
from django.conf import settings

class AssistantReview(models.Model):

    class Decision(models.TextChoices):
        APPROVE = "APPROVE"
        REJECT = "REJECT"

    paper = models.OneToOneField(
        ResearchPaper,
        on_delete=models.CASCADE,
        related_name="assistant_review"
    )

    assistant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={
            "role": "reviewer_assistant"
        }
    )

    notes = models.TextField()

    decision = models.CharField(
        max_length=20,
        choices=Decision.choices
    )

    reviewed_at = models.DateTimeField(
        auto_now_add=True
    )