from django.db import models
from accounts.models import User
from django.db import models
from .validators import validate_file_size


class ResearchPaper(models.Model):

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        ASSISTANT_REVIEW = "ASSISTANT_REVIEW", "Assistant Review"
        EDITOR_REVIEW = "EDITOR_REVIEW", "Editor Review"
        COMMITTEE_REVIEW = "COMMITTEE_REVIEW", "Committee Review"
        REVISION_REQUIRED = "REVISION_REQUIRED", "Revision Required"
        REJECTED = "REJECTED", "Rejected"
        ACCEPTED = "ACCEPTED", "Accepted"
        PUBLISHED = "PUBLISHED", "Published"

    research_id = models.AutoField(
        primary_key=True
    )

    title = models.CharField(
        max_length=300
    )

    abstract = models.TextField()

    paper_file = models.FileField(
        upload_to='papers/', validators=[validate_file_size]
    )

    publisher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="research_papers"
    )

    status = models.CharField(
        max_length=50,
        choices=Status.choices,
        default=Status.SUBMITTED
    )

    submission_date = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        db_table = "ResearchPaper"