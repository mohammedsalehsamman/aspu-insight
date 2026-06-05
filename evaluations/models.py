from django.db import models
from research.models import ResearchPaper
from accounts.models import User
from django.conf import settings


class Evaluation(models.Model):

    class Decision(models.TextChoices):
        ACCEPT = "ACCEPT"
        REJECT = "REJECT"
        MODIFY = "MODIFY"

    paper = models.ForeignKey(
        ResearchPaper,
        on_delete=models.CASCADE,
        related_name="evaluations"
    )

    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={
            "role": "reviewer"
        }
    )

    originality_score = models.DecimalField(
        max_digits=5,
        decimal_places=2
    )

    methodology_score = models.DecimalField(
        max_digits=5,
        decimal_places=2
    )

    scientific_value_score = models.DecimalField(
        max_digits=5,
        decimal_places=2
    )

    comments = models.TextField()

    decision = models.CharField(
        max_length=20,
        choices=Decision.choices
    )

    review_date = models.DateTimeField(
        auto_now_add=True
    )