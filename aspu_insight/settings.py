import os
from datetime import timedelta
from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-me-in-production')

DEBUG = False

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
    'ai_service',
    'dashboard',
    'notifications',
    'assistantReview',
    'editorReview',
    'configuration',
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

CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default=FRONTEND_URL, cast=Csv())
CORS_ALLOW_CREDENTIALS = True

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

CLAIM_EVIDENCE_EMBEDDING_MODEL = config(
    'CLAIM_EVIDENCE_EMBEDDING_MODEL',
    default=str(BASE_DIR / 'ai_service' / 'ml_models' / 'paraphrase-multilingual-MiniLM-L12-v2-base')
)
CLAIM_EVIDENCE_ZERO_SHOT_MODEL = config('CLAIM_EVIDENCE_ZERO_SHOT_MODEL', default='MoritzLaurer/mDeBERTa-v3-base-mnli-xnli')
CLAIM_EVIDENCE_SIMILARITY_THRESHOLD = config('CLAIM_EVIDENCE_SIMILARITY_THRESHOLD', default=0.2, cast=float)
CLAIM_EVIDENCE_TOP_CLAIMS_COUNT = config('CLAIM_EVIDENCE_TOP_CLAIMS_COUNT', default=10, cast=int)

IEEE_CHECKER_LLM_MODEL = config('IEEE_CHECKER_LLM_MODEL', default='Qwen/Qwen2.5-1.5B-Instruct')
IEEE_CHECKER_NER_MODEL = config('IEEE_CHECKER_NER_MODEL', default='dslim/bert-base-NER')
IEEE_CHECKER_MAX_LLM_REFS = config('IEEE_CHECKER_MAX_LLM_REFS', default=30, cast=int)
IEEE_CHECKER_ENABLE_SECTION_CHECK = config('IEEE_CHECKER_ENABLE_SECTION_CHECK', default=True, cast=bool)
IEEE_CHECKER_ENABLE_SEMANTIC_MATCH = config('IEEE_CHECKER_ENABLE_SEMANTIC_MATCH', default=True, cast=bool)
IEEE_CHECKER_SEMANTIC_MISMATCH_THRESHOLD = config('IEEE_CHECKER_SEMANTIC_MISMATCH_THRESHOLD', default=0.15, cast=float)

KEYWORD_EXTRACTOR_MODEL = config('KEYWORD_EXTRACTOR_MODEL', default=str(BASE_DIR / 'my-model'))

PLAGIARISM_EMBEDDING_MODEL = config(
    'PLAGIARISM_EMBEDDING_MODEL',
    default=str(BASE_DIR / 'ai_service' / 'ml_models' / 'experiments' / 'exp9-balanced-domain-APPROVED-BACKUP')
)
# النموذج الأساس غير المُضبَط دقيقاً — يُستخدَم لأي مقارنة عابرة للغات (عربي↔غير عربي) أو خارجية،
# لأن PLAGIARISM_EMBEDDING_MODEL المُضبَط دقيقاً أُحسِّن للعربية تحديداً وضعُف أداؤه الإنجليزي.
PLAGIARISM_BASE_EMBEDDING_MODEL = config(
    'PLAGIARISM_BASE_EMBEDDING_MODEL',
    default=str(BASE_DIR / 'ai_service' / 'ml_models' / 'paraphrase-multilingual-MiniLM-L12-v2-base')
)
# مفتاح اختياري ومجاني (سجّل على semanticscholar.org/product/api) — يمنح 1 طلب/ثانية مخصَّصاً
# بدل التنافس على المجمع المشترك غير المُصادَق عليه (1000 طلب/ثانية بين كل مستخدمي الإنترنت، يتشبَّع كثيراً).
SEMANTIC_SCHOLAR_API_KEY = config('SEMANTIC_SCHOLAR_API_KEY', default='')
PLAGIARISM_INTERNAL_SIMILARITY_THRESHOLD = config('PLAGIARISM_INTERNAL_SIMILARITY_THRESHOLD', default=0.75, cast=float)
PLAGIARISM_EXTERNAL_SIMILARITY_THRESHOLD = config('PLAGIARISM_EXTERNAL_SIMILARITY_THRESHOLD', default=0.6, cast=float)
# التصنيف ثنائي المستوى: أي تطابق بين هذا الحد والحد الأعلى (INTERNAL/EXTERNAL_SIMILARITY_THRESHOLD) يُصنَّف
# "مشتبه به يحتاج مراجعة بشرية" بدل تجاهله بالكامل — يعالج ضعف كشف إعادة الصياغة الحقيقية دون إعادة تدريب.
# القيمة 0.25 معايَرة تجريبياً على التوزيعين الفعليين (تقرير calibrate_two_tier_threshold.py) بحيث
# تلتقط أضعف حالة إعادة صياغة حقيقية مُختبَرة يدوياً (0.2667 على نموذج 9، 0.2985 على نموذج 10)، على
# حساب قبول نسبة أعلى من الإنذارات الكاذبة على أزواج غير مرتبطة أصلاً — مقبول لأنها للمراجعة لا للحكم.
PLAGIARISM_SUSPECTED_INTERNAL_THRESHOLD = config('PLAGIARISM_SUSPECTED_INTERNAL_THRESHOLD', default=0.25, cast=float)
PLAGIARISM_SUSPECTED_EXTERNAL_THRESHOLD = config('PLAGIARISM_SUSPECTED_EXTERNAL_THRESHOLD', default=0.25, cast=float)
# تصحيح لمشكلة المقارنات المتعددة (multiple comparisons): أخذ أعلى تشابه واحد فقط عبر عشرات مقاطع
# ورقتين كاملتين إحصائياً عرضة لتطابق عشوائي معزول (تأكَّد تجريبياً: 53-67% من عمليات فحص أوراق
# غير مرتبطة إطلاقاً أعطت "تأكيد" خاطئ واحداً على الأقل). لذلك "التأكيد" الآن يتطلب أدلة داعمة من
# أكثر من مقطع مستقل، لا مطابقة واحدة معزولة مهما علت قيمتها.
PLAGIARISM_CORROBORATION_THRESHOLD = config('PLAGIARISM_CORROBORATION_THRESHOLD', default=0.50, cast=float)
PLAGIARISM_MIN_CORROBORATING_CHUNKS = config('PLAGIARISM_MIN_CORROBORATING_CHUNKS', default=2, cast=int)
# ترجيح عكسي بتكرار العبارة (شبيه بفكرة IDF): مقطع يتشابه بشدة مع عدد كبير من مقاطع أخرى عبر
# مكتبة مرجعية (وليس فقط مع الورقة الأخرى قيد المقارنة) هو على الأرجح أسلوب أكاديمي شائع/صيغة
# متكرّرة، لا دليلاً خاصاً على النسخ بين ورقتين تحديداً — يُخفَّض تلقائياً لمستوى "مشتبه به".
# المكتبة المرجعية طبقتان: ملف ثابت (bootstrap) لأول انطلاقة للمجلة قبل توفر بيانات حقيقية كافية،
# بالإضافة لمقاطع كل الأبحاث الأخرى المُخزَّنة فعلياً في المنصة (تنمو تلقائياً مع كل بحث جديد).
PLAGIARISM_COMMONNESS_REFERENCE_PATH = config(
    'PLAGIARISM_COMMONNESS_REFERENCE_PATH',
    default=str(BASE_DIR / 'ai_service' / 'ml_models' / 'commonness_reference_arpd.npy')
)
# تحذير: 0.60/5 كانت القيمة الأولى المُختبَرة، وتبيَّن أنها كارثية عملياً (تُسقِط اكتشاف انتحال
# حقيقي فعلي من 100% إلى 6% فقط — راجع check_commonness_recall_impact.py). حتى 0.92 لا تزال تُسقِط
# الاسترجاع لنحو 67-77%. 0.97 هي أدنى قيمة رُصِد عندها استرجاع 99-100% على 865 زوجاً حقيقياً على
# كلا النموذجين — لا تُخفَّض دون إعادة اختبار الأثر على عيّنة انتحال حقيقية معروفة أولاً.
PLAGIARISM_COMMONNESS_THRESHOLD = config('PLAGIARISM_COMMONNESS_THRESHOLD', default=0.97, cast=float)
PLAGIARISM_COMMONNESS_MAX_COUNT = config('PLAGIARISM_COMMONNESS_MAX_COUNT', default=5, cast=int)
PLAGIARISM_CHUNK_SENTENCES = config('PLAGIARISM_CHUNK_SENTENCES', default=4, cast=int)
PLAGIARISM_CHUNK_OVERLAP = config('PLAGIARISM_CHUNK_OVERLAP', default=1, cast=int)
VALUESERP_API_KEY = config('VALUESERP_API_KEY', default='')
CORE_API_KEY = config('CORE_API_KEY', default='')

CELERY_TASK_ALWAYS_EAGER = config('CELERY_TASK_ALWAYS_EAGER', default=False, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = True

# لا يوجد Redis/Docker متاح في بيئات التطوير المحلية لهذا المشروع؛ ناقل الملفات
# (filesystem transport) يوفّر طابور رسائل حقيقياً بين عملية الويب وعامل Celery
# منفصل دون الحاجة لتثبيت أي خادم خارجي. يمكن التبديل لـ Redis لاحقاً بمجرد
# توفره عبر متغير البيئة CELERY_BROKER_URL دون أي تعديل كود.
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='filesystem://')
CELERY_BROKER_TRANSPORT_OPTIONS = {
    # يجب أن يكون نفس المجلد للطرفين (المُرسِل والعامل)؛ ناقل الملفات في kombu
    # يكتب من منظور "المُرسِل" في data_folder_out ويقرأ من منظور "العامل" في
    # data_folder_in - فإن اختلف المساران لا تلتقي الرسائل أبداً.
    'data_folder_in': str(BASE_DIR / 'celery_broker' / 'messages'),
    'data_folder_out': str(BASE_DIR / 'celery_broker' / 'messages'),
    'data_folder_processed': str(BASE_DIR / 'celery_broker' / 'processed'),
}
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='django-db')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    'check-committee-deadlines-daily': {
        'task': 'committees.tasks.check_committee_deadlines',
        'schedule': crontab(hour=0, minute=0),
    },
}

COMMITTEE_DEADLINE_DAYS = 15
