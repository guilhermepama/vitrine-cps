"""Configuração do Vitrine CPS (ADR-002).

Tudo que muda entre ambientes vem de variável de ambiente (ver .env.example).
Este arquivo é do coordenador: precisou mudar, peça (TAREFAS.md).
"""

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from config.env import carregar_env

BASE_DIR = Path(__file__).resolve().parent.parent

# Desenvolvimento local: lê o .env da raiz, se existir. Variável já definida
# no ambiente vence — em produção não há .env e nada muda.
carregar_env(BASE_DIR / ".env")


def env(nome, padrao=None, obrigatoria=False):
    valor = os.environ.get(nome, padrao)
    if obrigatoria and not valor:
        raise ImproperlyConfigured(
            f"Variável de ambiente {nome} não definida (ver .env.example)."
        )
    return valor


def env_bool(nome, padrao=False):
    valor = os.environ.get(nome)
    if valor is None or valor == "":
        return padrao
    return valor.strip().lower() in {"1", "true", "sim", "yes", "on"}


def env_lista(nome):
    return [item.strip() for item in os.environ.get(nome, "").split(",") if item.strip()]


# --- Núcleo ------------------------------------------------------------------

SECRET_KEY = env("DJANGO_SECRET_KEY", obrigatoria=True)

# HMAC do RA do representante (ADR-009). Separado do segredo do QR: um
# vazamento não compromete o outro.
RA_HMAC_SECRET = env("RA_HMAC_SECRET", obrigatoria=True)
DEBUG = env_bool("DJANGO_DEBUG")

ALLOWED_HOSTS = env_lista("DJANGO_ALLOWED_HOSTS")
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Origem com esquema, ex: https://vitrine.exemplo.com.br (exigido pelo CSRF atrás de HTTPS)
CSRF_TRUSTED_ORIGINS = env_lista("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    # Uma frente por app (TAREFAS.md)
    "cadastro",
    "vitrine",
    "votacao",
    "banca",
    "resultados",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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

# --- Banco (ADR-002: PostgreSQL em todo ambiente que roda teste ou produção) --

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", obrigatoria=True),
        conn_max_age=60,
        conn_health_checks=True,
    )
}
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured(
        "DATABASE_URL precisa apontar para PostgreSQL. SQLite não reproduz a "
        "concorrência do voto (guardrail 4, ADR-002)."
    )

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Cache -------------------------------------------------------------------
# Compartilhado entre os workers do gunicorn: o rate limit (guardrail 7) conta
# requisições no cache, e um cache por processo (LocMem) deixaria cada worker
# com o próprio contador. No deploy: `python manage.py createcachetable`.

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cache_django",
    }
}

# --- Senhas do admin ---------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Idioma e fuso -----------------------------------------------------------

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# --- Arquivos estáticos (whitenoise) e mídia ---------------------------------
# Imagens dos projetos: Cloudflare R2 quando R2_BUCKET está definido
# (ADR-006); sem ele, disco local (desenvolvimento).

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

if env("R2_BUCKET"):
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("R2_BUCKET"),
            "endpoint_url": f"https://{env('R2_ACCOUNT_ID', obrigatoria=True)}.r2.cloudflarestorage.com",
            "access_key": env("R2_ACCESS_KEY_ID", obrigatoria=True),
            "secret_key": env("R2_SECRET_ACCESS_KEY", obrigatoria=True),
            "region_name": "auto",
            "signature_version": "s3v4",
            # URL pública pelo domínio próprio, sem assinatura: a prévia do
            # WhatsApp precisa de um link que não expira (ADR-006).
            "custom_domain": env("R2_PUBLIC_DOMAIN", obrigatoria=True),
            "querystring_auth": False,
            "file_overwrite": False,
        },
    }

# --- Segurança em produção ---------------------------------------------------

if not DEBUG:
    # A plataforma de hospedagem termina o HTTPS e repassa o esquema neste cabeçalho.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Ligar quando a plataforma não redirecionar HTTP→HTTPS sozinha.
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT")
    SECURE_REDIRECT_EXEMPT = [r"^saude/$"]

# --- Logs --------------------------------------------------------------------
# Só no console (a plataforma coleta). Sem DEBUG, o Django por padrão manda
# erros só por e-mail — aqui eles aparecem no log. Nunca logar token, RA ou
# dado de visitante (guardrails 3 e 11).

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", "INFO"), "propagate": False},
    },
}
