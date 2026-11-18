"""
Django settings for the National Arts Council of Botswana (NACB) Digital Platform.

All deployment-specific values are read from environment variables so the same
code base runs in development, staging and production (see .env.example).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return str(env(name, default)).lower() in ("1", "true", "yes", "on")


ON_VERCEL = bool(env("VERCEL"))  # set automatically by Vercel

SECRET_KEY = env("NACB_SECRET_KEY", "dev-insecure-change-me-7c1f0a2b9d4e")
DEBUG = env_bool("NACB_DEBUG", not ON_VERCEL)
if ON_VERCEL and SECRET_KEY.startswith("dev-insecure"):
    raise RuntimeError("Set NACB_SECRET_KEY in the Vercel project settings.")
ALLOWED_HOSTS = [h.strip() for h in env("NACB_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("NACB_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]
if ON_VERCEL:
    ALLOWED_HOSTS += [".vercel.app"]
    CSRF_TRUSTED_ORIGINS += ["https://*.vercel.app"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # NACB apps
    "accounts",
    "portal",
    "grants",
    "events",
    "endorsements",
    "backoffice",
    "partnerships",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.MFAEnforcementMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "portal.middleware.SecurityHeadersMiddleware",
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
                "portal.context_processors.site_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database: SQLite for development. Hosted: DATABASE_URL (postgres://user:pass@host:port/db) or NACB_DB_* settings.
if env("DATABASE_URL"):
    from urllib.parse import unquote, urlparse
    _u = urlparse(env("DATABASE_URL"))
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _u.path.lstrip("/") or "postgres",
            "USER": unquote(_u.username or ""),
            "PASSWORD": unquote(_u.password or ""),
            "HOST": _u.hostname,
            "PORT": str(_u.port or 5432),
            # Serverless: short-lived connections through the pooler; no persistent connections.
            "CONN_MAX_AGE": 0,
            "DISABLE_SERVER_SIDE_CURSORS": True,  # safe behind a transaction-mode pooler
            "OPTIONS": {"sslmode": "require"},
        }
    }
elif env("NACB_DB_ENGINE", "sqlite") == "postgresql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("NACB_DB_NAME", "nacb"),
            "USER": env("NACB_DB_USER", "nacb"),
            "PASSWORD": env("NACB_DB_PASSWORD", ""),
            "HOST": env("NACB_DB_HOST", "localhost"),
            "PORT": env("NACB_DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
            "CONN_HEALTH_CHECKS": True,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            # WAL + immediate transactions let many concurrent requests write safely (dev/pilot only).
            "OPTIONS": {"timeout": 60, "transaction_mode": "IMMEDIATE",
                        "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;"},
        }
    }

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "portal:dashboard"
LOGOUT_REDIRECT_URL = "portal:home"

# Strong password policy (FR-2.3)
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "accounts.validators.ComplexityValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Gaborone"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# WhiteNoise serves static files from the app itself (works on Vercel and any WSGI host).
WHITENOISE_USE_FINDERS = True
WHITENOISE_MAX_AGE = 60 * 60 * 24

# Public media (news images, gallery, published resources)
MEDIA_URL = "media/"
MEDIA_ROOT = Path("/tmp/media") if ON_VERCEL else BASE_DIR / "media"
# Private documents (IDs, bank letters, proposals) are stored OUTSIDE the public
# media root and only served through permission-checked views.
PRIVATE_MEDIA_ROOT = Path(env("NACB_PRIVATE_MEDIA_ROOT", "/tmp/private_media" if ON_VERCEL else BASE_DIR / "private_media"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Uploads (FR-4.2 / 4.1 UI): size and type restrictions
MAX_UPLOAD_MB = int(env("NACB_MAX_UPLOAD_MB", 5))
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
ALLOWED_DOCUMENT_EXTENSIONS = ["pdf", "jpg", "jpeg", "png", "doc", "docx", "xls", "xlsx"]
ALLOWED_PORTFOLIO_EXTENSIONS = ["pdf", "jpg", "jpeg", "png", "gif", "webp", "mp3", "mp4", "doc", "docx"]

# Email (FR-8.1). Console backend in development; SMTP / transactional provider in production.
EMAIL_BACKEND = env("NACB_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("NACB_EMAIL_HOST", "localhost")
EMAIL_PORT = int(env("NACB_EMAIL_PORT", 587))
EMAIL_HOST_USER = env("NACB_EMAIL_USER", "")
EMAIL_HOST_PASSWORD = env("NACB_EMAIL_PASSWORD", "")
EMAIL_USE_TLS = env_bool("NACB_EMAIL_TLS", True)
DEFAULT_FROM_EMAIL = env("NACB_FROM_EMAIL", "NACB Digital Services <no-reply@nacb.org.bw>")

# SMS gateway (optional). "console" logs messages; "http" posts to NACB_SMS_URL.
SMS_BACKEND = env("NACB_SMS_BACKEND", "console")
SMS_URL = env("NACB_SMS_URL", "")
SMS_API_KEY = env("NACB_SMS_API_KEY", "")
SMS_SENDER_ID = env("NACB_SMS_SENDER", "NACB")

SITE_URL = env("NACB_SITE_URL", "http://127.0.0.1:8000")

# Footer credit
DEVELOPER_NAME = "Cyberjaya Investments (Pty) Ltd"
DEVELOPER_URL = env("NACB_DEVELOPER_URL", "https://www.cyberjayainvest.com/")

# Session & security hardening (OWASP)
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15
# Staff roles must enrol in MFA when this is on (recommended for production)
REQUIRE_STAFF_MFA = env_bool("NACB_REQUIRE_STAFF_MFA", False)

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("NACB_SSL_REDIRECT", not ON_VERCEL)  # Vercel already forces HTTPS
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------- Capacity (1000+ concurrent sign-ins)
# The cache holds sessions, login-lockout counters and rate limits, so it MUST be shared by every worker process.
# Production: Redis (NACB_REDIS_URL). Fallback: a database cache table (`python manage.py createcachetable`).
if env("NACB_REDIS_URL"):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": env("NACB_REDIS_URL"),
                          "TIMEOUT": 60 * 60 * 8}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "nacb_cache",
                          "OPTIONS": {"MAX_ENTRIES": 200000, "CULL_FREQUENCY": 4}}}
# Sessions are read from the shared cache and persisted to the database (survive restarts, scale across servers).
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
SESSION_SAVE_EVERY_REQUEST = False
# Password hashing cost: PBKDF2 default (~1M iterations). Each sign-in costs ~0.2 to 0.4 CPU-seconds by design
# (brute-force protection); size CPU cores for peak sign-in bursts (see docs/CAPACITY.md).

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "nacb": {"handlers": ["console"], "level": "INFO"},
    },
}
