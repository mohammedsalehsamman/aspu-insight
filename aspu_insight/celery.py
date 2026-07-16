import os
<<<<<<< HEAD
=======

>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aspu_insight.settings')

app = Celery('aspu_insight')

<<<<<<< HEAD
app.conf.update(
    broker_transport_options={
        'socket_connect_timeout': 10,
        'socket_timeout': 10,
        'health_check_interval': 10,
    }
)

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
=======
# Read CELERY_* settings from Django settings.py, using the CELERY_ namespace.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks.py in each installed app.
app.autodiscover_tasks()
>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5
