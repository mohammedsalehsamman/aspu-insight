from django.db import models
from research.models import ResearchPaper
from django.conf import settings

class ReviewerInvitation(models.Model):

    class Status(models.TextChoices):

        PENDING = "PENDING"

        ACCEPTED = "ACCEPTED"

        DECLINED = "DECLINED"

    paper = models.ForeignKey(
        ResearchPaper,
        on_delete=models.CASCADE,
        related_name="reviewer_invitations"
    )

    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="review_invitations"
    )

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_review_invitations"
    )

    invitation_message = models.TextField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    invited_at = models.DateTimeField(
        auto_now_add=True
    )

    responded_at = models.DateTimeField(
        null=True,
        blank=True
    )