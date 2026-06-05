from django.db import models
from research.models import ResearchPaper
from django.conf import settings

class ResearchHistory(models.Model):

    paper = models.ForeignKey(
        ResearchPaper,
        on_delete=models.CASCADE,
        related_name="history"
    )

    from_status = models.CharField(
        max_length=50
    )

    to_status = models.CharField(
        max_length=50
    )

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    note = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )
