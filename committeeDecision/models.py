from django.db import models
from research.models import ResearchPaper


class CommitteeDecision(models.Model):

    class Decision(models.TextChoices):

        ACCEPT = "ACCEPT"

        REJECT = "REJECT"

        MODIFY = "MODIFICATION"

    paper = models.OneToOneField(
        ResearchPaper,
        on_delete=models.CASCADE
    )

    decision = models.CharField(
        max_length=20,
        choices=Decision.choices
    )

    notes = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )