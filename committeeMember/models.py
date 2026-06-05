from django.db import models
from committees.models import Committee
from accounts.models import User

class CommitteeMember(models.Model):

    committee = models.ForeignKey(
        Committee,
        on_delete=models.CASCADE,
        related_name="members"
    )

    reviewer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={
            "role": "reviewer"
        }
    )