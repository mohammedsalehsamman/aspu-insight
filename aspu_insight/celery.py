import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aspu_insight.settings')

app = Celery('aspu_insight')

app.conf.update(
    broker_transport_options={
        'socket_connect_timeout': 10,
        'socket_timeout': 10,
        'health_check_interval': 10,
    }
)

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()