import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aspu_insight.settings')

app = Celery('aspu_insight')

# Read CELERY_* settings from Django settings.py, using the CELERY_ namespace.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks.py in each installed app.
app.autodiscover_tasks()
