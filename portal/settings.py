"""Django settings for the school educational portal."""

import json
import os
import sys
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

from school_portal.ad_config import get_ad_config

BASE_DIR = Path(__file__).resolve().parent.parent
DOTENV_SETTINGS = dotenv_values(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default):
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", os.getenv("SECRET_KEY", "replace-me-with-a-strong-secret"))
DEBUG = env_bool("DEBUG", True)
RUNNING_DJANGO_DEV_SERVER = len(sys.argv) > 1 and sys.argv[1] == "runserver"
ALLOWED_HOSTS = list(dict.fromkeys(
    host.strip()
    for source in (os.getenv("ALLOWED_HOSTS", ""), DOTENV_SETTINGS.get("ALLOWED_HOSTS", "localhost,127.0.0.1"))
    for host in str(source or "").split(",")
    if host.strip()
))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "school_portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "portal.urls"

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

WSGI_APPLICATION = "portal.wsgi.application"

if os.getenv("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "portal"),
            "USER": os.getenv("POSTGRES_USER", "portal"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "portal"),
            "HOST": os.getenv("POSTGRES_HOST", "portal-db"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "ar"
LANGUAGE_CODE_EN = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.console.EmailBackend",
    },
}

AUTHENTICATION_BACKENDS = [
    "school_portal.auth_backend.ADBackend",
    "django.contrib.auth.backends.ModelBackend",
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG and not RUNNING_DJANGO_DEV_SERVER)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG and not RUNNING_DJANGO_DEV_SERVER)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG and not RUNNING_DJANGO_DEV_SERVER)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 900
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

SESSION_ENGINE = "django.contrib.sessions.backends.db"

LOGIN_RATE_LIMIT = int(os.getenv("LOGIN_RATE_LIMIT", "5"))
LOGIN_RATE_WINDOW_MINUTES = int(os.getenv("LOGIN_RATE_WINDOW_MINUTES", "15"))

AD_CONFIG = get_ad_config()
AD_SERVER = AD_CONFIG.AD_SERVER
AD_HOSTNAME = AD_CONFIG.AD_HOSTNAME
AD_DOMAIN = AD_CONFIG.AD_DOMAIN
AD_NETBIOS_DOMAIN = AD_CONFIG.AD_NETBIOS_DOMAIN
AD_PORT = int(AD_CONFIG.AD_PORT or 389)
AD_LDAPS_PORT = AD_CONFIG.AD_LDAPS_PORT
AD_USE_SSL = AD_CONFIG.AD_USE_SSL
AD_USE_STARTTLS = AD_CONFIG.AD_USE_STARTTLS
AD_LDAP_SERVER = os.getenv("AD_LDAP_SERVER", AD_HOSTNAME).strip()
AD_LDAP_ENCRYPTION = AD_CONFIG.AD_LDAP_ENCRYPTION
AD_LDAP_CA_CERTS_FILE = AD_CONFIG.AD_LDAP_CA_CERTS_FILE
AD_AUTH_METHOD = AD_CONFIG.AD_AUTH_METHOD
AD_USER_SEARCH_FILTER = os.getenv(
    "AD_USER_SEARCH_FILTER",
    "(&(objectCategory=person)(objectClass=user)(sAMAccountName={username}))",
).strip()
AD_BASE_DN = AD_CONFIG.AD_BASE_DN
AD_USER_SEARCH_BASE = AD_CONFIG.AD_USER_SEARCH_BASE
AD_GROUP_SEARCH_BASE = AD_CONFIG.AD_GROUP_SEARCH_BASE
AD_BIND_USERNAME = AD_CONFIG.AD_BIND_USERNAME
AD_BIND_PASSWORD = AD_CONFIG.AD_BIND_PASSWORD
AD_TEST_USERNAME = AD_CONFIG.AD_TEST_USERNAME
AD_SEARCH_BASE = AD_BASE_DN
FILE_SERVER = os.getenv("FILE_SERVER", "").strip()
FILE_SERVER_IP = os.getenv("FILE_SERVER_IP", "").strip()
DISPLAY_OS = os.getenv("DISPLAY_OS", "windows").strip() or "windows"
SHARE_MOUNT_ROOT = os.path.abspath(os.getenv("SHARE_MOUNT_ROOT", "/app/shares").strip() or "/app/shares")
# Index 0 is the user's nearest OU in the leaf-first DN. Adjust after confirming a real DN.
try:
    LDAP_OU_DEPTH_INDEX = max(0, int(os.getenv("LDAP_OU_DEPTH_INDEX", "0")))
except ValueError:
    LDAP_OU_DEPTH_INDEX = 0

try:
    _ou_subject_map = json.loads(os.getenv("OU_SUBJECT_MAP", "{}"))
except ValueError:
    _ou_subject_map = {}
OU_SUBJECT_MAP = {
    str(ou_name): [path for path in paths if isinstance(path, str)]
    for ou_name, paths in (_ou_subject_map.items() if isinstance(_ou_subject_map, dict) else [])
    if isinstance(ou_name, str) and isinstance(paths, list)
}

AD_CONFIG_READY = AD_CONFIG.is_ready
AD_CONFIG_ERRORS = list(AD_CONFIG.missing_fields)
AD_AUTH_CONFIG_ERRORS = []
if AD_LDAP_ENCRYPTION not in {"starttls", "ldaps"}:
    AD_AUTH_CONFIG_ERRORS.append("AD_LDAP_ENCRYPTION (starttls or ldaps)")
if AD_AUTH_METHOD not in {"NTLM", "SIMPLE"}:
    AD_AUTH_CONFIG_ERRORS.append("AD_AUTH_METHOD (NTLM or SIMPLE)")
if AD_AUTH_METHOD == "NTLM" and not AD_NETBIOS_DOMAIN:
    AD_AUTH_CONFIG_ERRORS.append("AD_NETBIOS_DOMAIN (required for NTLM)")
AD_AUTH_READY = AD_CONFIG_READY and not AD_AUTH_CONFIG_ERRORS

DEFAULT_AD_SHARE_GROUPS = {}
AD_SHARE_GROUPS = {}
raw_share_groups = os.getenv("AD_SHARE_GROUPS", "")
if raw_share_groups.strip():
    try:
        AD_SHARE_GROUPS = json.loads(raw_share_groups)
    except ValueError:
        AD_SHARE_GROUPS = {}
