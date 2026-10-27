"""Django configuration. Production requires explicit secrets and HTTPS settings."""

import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured

from .openapi import AUTH_PATHS
from .runtime_secrets import read_secret
from .upload_limits import configured_upload_bytes

BASE_DIR = Path(__file__).resolve().parent.parent
TESTING = os.getenv("DJANGO_TESTING") == "1"
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
SECRET_KEY = read_secret("DJANGO_SECRET_KEY", "test-only-not-for-deployment" if TESTING else "")
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is required")

ALLOWED_HOSTS = [
    s.strip()
    for s in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if s.strip()
]
AUDIT_TRUSTED_PROXY_CIDRS = [
    item.strip() for item in os.getenv(
        "AUDIT_TRUSTED_PROXY_CIDRS", "172.16.0.0/12,127.0.0.1/32"
    ).split(",") if item.strip()
]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must not be empty")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "axes",
    "corsheaders",
    "apps.accounts",
    "apps.meetings",
    "apps.audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "config.middleware.SessionVersionMiddleware",
    "apps.audit.middleware.MutationAuditMiddleware",
    "config.middleware.InitialPasswordMiddleware",
    "apps.meetings.services.upload_capacity.UploadCapacityMiddleware",
    "axes.middleware.AxesMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

if os.getenv("DATABASE_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DATABASE_NAME", "audio"),
            "USER": os.getenv("DATABASE_USER", "audio"),
            "PASSWORD": read_secret("DATABASE_PASSWORD"),
            "HOST": os.environ["DATABASE_HOST"],
            "PORT": os.getenv("DATABASE_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "dev.sqlite3"}
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_RESET_ON_SUCCESS = True
# Docker/Nginx can collapse many users to one proxy/NAT address. A standalone
# IP lockout lets five guesses against arbitrary names block every account.
# Pair username and IP rather than applying independent global IP lockout.
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", BASE_DIR / "media")).resolve()
FILE_UPLOAD_TEMP_DIR = str(MEDIA_ROOT / "tmp") if os.getenv("DATABASE_HOST") else None
if FILE_UPLOAD_TEMP_DIR:
    Path(FILE_UPLOAD_TEMP_DIR).mkdir(parents=True, exist_ok=True, mode=0o700)
MAX_UPLOAD_BYTES = configured_upload_bytes(os.getenv("MAX_UPLOAD_MB", "5120"))
MAX_INFLIGHT_UPLOADS = 1  # leaves two of the three synchronous HTTP workers available
STAGED_UPLOAD_MAX_BYTES = int(os.getenv("STAGED_UPLOAD_MAX_MB", "20480")) * 1024**2
STAGED_UPLOAD_MAX_BYTES_PER_USER = int(os.getenv("STAGED_UPLOAD_USER_MAX_MB", "10240")) * 1024**2
MEDIA_MIN_FREE_BYTES = int(os.getenv("MEDIA_MIN_FREE_MB", "1024")) * 1024**2
if min(STAGED_UPLOAD_MAX_BYTES, STAGED_UPLOAD_MAX_BYTES_PER_USER) <= 0 or MEDIA_MIN_FREE_BYTES < 0:
    raise ImproperlyConfigured("Invalid staging capacity limits")
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
FILE_UPLOAD_HANDLERS = [
    "config.uploads.SizeLimitUploadHandler",
    "django.core.files.uploadhandler.MemoryFileUploadHandler",
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]
FFMPEG_TIMEOUT_SECONDS = int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "3600"))
SECTOR_KEY_ENCRYPTION_KEY = read_secret("SECTOR_KEY_ENCRYPTION_KEY")
MODELO_TRANSCRICAO = os.getenv("MODELO_TRANSCRICAO", "gpt-4o-transcribe-diarize")
TRANSCRIPTION_LANGUAGE = os.getenv("TRANSCRIPTION_LANGUAGE", "").strip()
MODELO_ATA = os.getenv("MODELO_ATA", "gpt-6-luna")
MODELO_MAPA = os.getenv("MODELO_MAPA", "gpt-6-luna")
MODELO_CORRECAO = os.getenv("MODELO_CORRECAO", "gpt-4.1-mini")
AI_PROVIDER_TRANSCRIPTION = os.getenv("AI_PROVIDER_TRANSCRIPTION", "openai")
AI_PROVIDER_MINUTES = os.getenv("AI_PROVIDER_MINUTES", "openai")
AI_PROVIDER_MIND_MAP = os.getenv("AI_PROVIDER_MIND_MAP", "openai")
AI_PROVIDER_CORRECTION = os.getenv("AI_PROVIDER_CORRECTION", "openai")

_redis_password = read_secret("REDIS_PASSWORD")
REDIS_URL = os.getenv("REDIS_URL") or (
    f"redis://:{quote(_redis_password, safe='')}@redis:6379/0"
    if _redis_password else "redis://localhost:6379/0"
)
HEALTH_FRONTEND_URL = os.getenv("HEALTH_FRONTEND_URL", "http://frontend:8080/healthz")
HEALTH_BACKEND_URL = os.getenv("HEALTH_BACKEND_URL", "http://backend:8000/health/")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = None
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 1800
CELERY_TASK_SOFT_TIME_LIMIT = 1700
AUDIT_RETENTION_DAYS = 90
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "admin-health-every-five-minutes": {
        "task": "audit.collect_health_sample",
        "schedule": 300.0,
    },
    "audit-retention-daily": {
        "task": "audit.prune_expired_events",
        "schedule": crontab(hour=3, minute=15),
    },
    "meeting-purge-hourly": {
        "task": "meetings.purge_expired",
        "schedule": crontab(minute=0),
    },
    "staged-upload-purge-every-five-minutes": {
        "task": "meetings.purge_staged_uploads",
        "schedule": 300.0,
    },
}
TRANSCRIPTION_TIME_MULTIPLIER = float(os.getenv("TRANSCRIPTION_TIME_MULTIPLIER", "2.0"))
TRANSCRIPTION_MIN_SOFT_SECONDS = int(os.getenv("TRANSCRIPTION_MIN_SOFT_SECONDS", "3600"))
TRANSCRIPTION_HARD_GRACE_SECONDS = int(os.getenv("TRANSCRIPTION_HARD_GRACE_SECONDS", "600"))
TRANSCRIPTION_PARALLELISM = int(os.getenv("TRANSCRIPTION_PARALLELISM", "10"))
TRANSCRIPTION_REQUEST_TIMEOUT_SECONDS = int(
    os.getenv("TRANSCRIPTION_REQUEST_TIMEOUT_SECONDS", "900")
)
CELERY_TASK_ALWAYS_EAGER = TESTING
CELERY_TASK_EAGER_PROPAGATES = TESTING

if TESTING:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
else:
    CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}
    }

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": ["apps.meetings.throttles.AvailableUserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": "120/min", "upload": "4/hour"},
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "config.errors.exception_handler",
    "URL_FORMAT_OVERRIDE": None,
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Scribrief API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "APPEND_PATHS": AUTH_PATHS,
}

secure_cookies = (
    os.getenv("DJANGO_SECURE_COOKIES", "true" if not TESTING else "false").lower() == "true"
)
SESSION_COOKIE_SECURE = secure_cookies
CSRF_COOKIE_SECURE = secure_cookies
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # The SPA must read this token and send X-CSRFToken.
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_HSTS_SECONDS = 31536000 if os.getenv("DJANGO_ENABLE_HSTS") == "true" else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_SSL_REDIRECT = os.getenv("DJANGO_FORCE_HTTPS") == "true"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
CORS_ALLOWED_ORIGINS = [FRONTEND_ORIGIN] if DEBUG else []
CORS_ALLOW_CREDENTIALS = DEBUG
CSRF_TRUSTED_ORIGINS = [FRONTEND_ORIGIN] if DEBUG else []

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}
