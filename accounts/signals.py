import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User
from .utils import create_token_for_user, send_email_verification

logger = logging.getLogger(__name__)

@receiver(post_save, sender=User)
def send_verification_email_on_register(sender, instance, created, **kwargs):

    pass
