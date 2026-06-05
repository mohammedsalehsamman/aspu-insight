from django.db import models
from research.models import ResearchPaper

class Committee(models.Model):


    paper = models.OneToOneField(
        ResearchPaper,
        on_delete=models.CASCADE,
        related_name="committee"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )