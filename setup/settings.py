"""
Django settings for setup project.
"""
import os
import dj_database_url
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================
# SEGURANÇA
# ============================================
SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-dev-key"
)

DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

# Backend do Render + localhost
ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "selezione-onboarding-api.onrender.com",
]

# ============================================
# CACHE
# ============================================
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    }
}

# ============================================
# APPS
# ============================================
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "rest_framework",
    "corsheaders",
    "onboarding",
]

# ============================================
# MIDDLEWARE
# ============================================
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # precisa vir primeiro
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# ============================================
# CORS (Vercel production + previews)
# ============================================
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.vercel\.app$",
]

# Se quiser deixar a URL fixa principal também
CORS_ALLOWED_ORIGINS = [
    "https://selezione-onboarding.vercel.app",
]

CORS_ALLOW_CREDENTIALS = True

# ============================================
# AUTH
# ============================================
AUTH_USER_MODEL = "onboarding.CustomUser"
AUTHENTICATION_BACKENDS = [
    "onboarding.api.v1.backends.EmailBackend"
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ============================================
# DATABASE
# ============================================
DATABASES = {
    "default": dj_database_url.config(
        default="sqlite:///" + str(BASE_DIR / "db.sqlite3"),
        conn_max_age=600,
    )
}

# ============================================
# TEMPLATES
# ============================================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ============================================
# STATIC
# ============================================
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_STORAGE = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
)

# ============================================
# MEDIA
# ============================================
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ============================================
# URLS
# ============================================
ROOT_URLCONF = "setup.urls"
WSGI_APPLICATION = "setup.wsgi.application"

# ============================================
# INTERNACIONALIZAÇÃO
# ============================================
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# ============================================
# PASSWORDS
# ============================================
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
]

# ============================================
# PRODUÇÃO
# ============================================
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True