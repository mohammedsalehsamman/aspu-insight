import os
from datetime import timedelta
from pathlib import Path 
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'SECRET_KEY'

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_celery_results',
    'axes' ,
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'accounts',
    'research',
    'committees',
    'evaluations',
    'ai_service',
    'dashboard',
    'notifications',
    'assistantReview',
    'editorReview',
    'configuration',
    'reviewerinvitation',
    'researchHistory'
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware'
]

ROOT_URLCONF = 'aspu_insight.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'aspu_insight.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_USER_MODEL = 'accounts.User'

AUTHENTICATION_BACKENDS = [
    'accounts.backends.EmailBackend',
    'django.contrib.auth.backends.ModelBackend',
    'axes.backends.AxesStandaloneBackend',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'user_id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
}

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='ASPU Insight <noreply@aspu-insight.dz>')

FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:3000')
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

SPECTACULAR_SETTINGS = {
    'TITLE': 'ASPU Insight API',
    'DESCRIPTION': 'ASPU Insight ',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

AXES_FAILURE_LIMIT = 4            
AXES_COOLOFF_TIME = 2                   
AXES_RESET_ON_SUCCESS = True

HF_HOME = str(BASE_DIR / '.hf_cache')
os.environ.setdefault('HF_HOME', HF_HOME)

CLAIM_EVIDENCE_EMBEDDING_MODEL = config('CLAIM_EVIDENCE_EMBEDDING_MODEL', default='sentence-transformers/all-MiniLM-L6-v2')
CLAIM_EVIDENCE_ZERO_SHOT_MODEL = config('CLAIM_EVIDENCE_ZERO_SHOT_MODEL', default='valhalla/distilbart-mnli-12-3')
CLAIM_EVIDENCE_SIMILARITY_THRESHOLD = config('CLAIM_EVIDENCE_SIMILARITY_THRESHOLD', default=0.5, cast=float)
CLAIM_EVIDENCE_TOP_CLAIMS_COUNT = config('CLAIM_EVIDENCE_TOP_CLAIMS_COUNT', default=10, cast=int)

# في ملف settings.py التابع للمجلد aspu_insight

# 1. روابط نظيفة تماماً بدون أي علامات استفهام
CELERY_BROKER_URL = 'redis://127.0.0.1:6379/0'
CELERY_RESULT_BACKEND = 'redis://127.0.0.1:6379/0'

# 2. الحل السحري النهائي لمنع بروتوكول RESP3 وإلغاء أمر HELLO نهائياً
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'global_keyprefix': 'aspu_',
    'connection_class': 'redis.connection.Connection',  # إجبار على الكلاس الكلاسيكي المتوافق مع ويندوز
}

CELERY_REDIS_BACKEND_TRANSPORT_OPTIONS = {
    'global_keyprefix': 'aspu_res_',
    'connection_class': 'redis.connection.Connection',
}
from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    'check-committee-deadlines-daily': {
        'task': 'committees.tasks.check_committee_deadlines',
        'schedule': crontab(hour=0, minute=0),
    },
}

COMMITTEE_DEADLINE_DAYS = 15