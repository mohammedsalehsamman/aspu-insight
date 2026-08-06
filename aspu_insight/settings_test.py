from .settings import *
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

CELERY_BROKER_URL = 'memory://'

FIREBASE_CREDENTIALS_PATH = ''

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
