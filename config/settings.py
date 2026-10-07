"""Configuração do Vitrine CPS (ADR-002).

Tudo que muda entre ambientes vem de variável de ambiente (ver .env.example).
Este arquivo é do coordenador: precisou mudar, peça (TAREFAS.md).
"""

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from config.env import carregar_env, url_publica

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

# Votação (spec 03). Três segredos distintos: QR assina as janelas das
# estações; IP vira HMAC na chave do rate limit (o IP em claro nunca vai
# para o cache, que entra no pg_dump). Um vazamento não compromete o outro.
QR_HMAC_SECRET = env("QR_HMAC_SECRET", obrigatoria=True)
IP_HMAC_SECRET = env("IP_HMAC_SECRET", obrigatoria=True)
# Cabeçalho com o IP real do cliente atrás do proxy (ADR-006), ex.:
# "X-Forwarded-For". Vazio = REMOTE_ADDR (desenvolvimento e CI). Só preencher
# com um cabeçalho que o proxy da hospedagem reescreve — senão o cliente
# manda um IP falso e fura o rate limit. Lido em cadastro.seguranca.ip_do_cliente.
IP_HEADER = env("DJANGO_IP_HEADER", "")
DEBUG = env_bool("DJANGO_DEBUG")

ALLOWED_HOSTS = env_lista("DJANGO_ALLOWED_HOSTS")
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Origem pública do site, ex.: https://vitrine.exemplo.com.br (ADR-006).
# Base dos links absolutos, como o QR das estações (spec 03): não depende do
# Host da requisição nem do X-Forwarded-Proto. Obrigatória sem DEBUG.
URL_PUBLICA = url_publica(env("DJANGO_URL_PUBLICA", ""), DEBUG)

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
#
# MAX_ENTRIES: o padrão do Django (300) faz o cache, ao passar de 300 linhas,
# apagar ~1/3 das chaves VIVAS em ordem alfabética — os contadores do rate
# limit somem e quem estava barrado volta a passar (parecer do PR #34). Com
# ~300 IPs distintos em 10 min (4G, IPv6) isso já acontece. As expiradas
# saem primeiro; o teto alto só evita crescer sem fim.

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cache_django",
        "OPTIONS": {"MAX_ENTRIES": 100_000},
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
# CSS da identidade visual (static/css/base.css), compartilhado por todos os apps.
STATICFILES_DIRS = [BASE_DIR / "static"]
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
#
# P2 (spec 03, B1): nas rotas do visitante (/entrar, /visitantes, /votar,
# /votos) nenhuma linha por request; 5xx sai reescrito, sem a mensagem da
# exceção. O filtro fica em dois lugares:
# - no handler `console`: pega os django.security.<Classe> do
#   SuspiciousOperation, que o Django nomeia pela exceção e não dá para listar;
# - nos loggers: assertLogs troca os handlers, então só o filtro de logger vale
#   nos testes. Filtro de logger não pega o que propaga dos filhos — por isso
#   django.security.csrf entra pelo nome.
# O registro reescrito já não tem `request` e passa direto na segunda vez.
# DJANGO_LOG_LEVEL=DEBUG só em máquina local: com DEBUG=True o
# django.db.backends loga o SQL com os parâmetros (nome e email do visitante),
# e esse registro não tem `request` — o filtro não o alcança.
#
# Link de edição do grupo (spec 02): em /grupo/editar/<token>/ o caminho leva o
# token. O filtro `token_edicao` (config/logs.py) troca o segmento por
# "<token>", nos mesmos lugares do filtro do visitante.
#
# django.template fica em INFO mesmo com DJANGO_LOG_LEVEL=DEBUG: em DEBUG ele
# loga a variável que falta no contexto, e o contexto da cédula e do cadastro
# tem dado do visitante (parecer do PR #36).

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "rotas_visitante": {"()": "votacao.logs.FiltroRotasVisitante"},
        "token_edicao": {"()": "config.logs.FiltroTokenEdicao"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "filters": ["rotas_visitante", "token_edicao"]},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", "INFO"), "propagate": False},
        "django.request": {"filters": ["rotas_visitante", "token_edicao"]},
        "django.security": {"filters": ["rotas_visitante", "token_edicao"]},
        "django.security.csrf": {"filters": ["rotas_visitante", "token_edicao"]},
        "django.template": {"level": "INFO"},
        "votacao": {"filters": ["rotas_visitante"]},
        # Registro do export de visitantes (spec 04, parecer do #57): INFO,
        # acima do root. Sem handler próprio: propaga ao console, que aplica
        # os filtros P2, e não duplica a linha. (Filtro de logger não pegaria
        # os registros de resultados.views, que é filho.)
        "resultados": {"level": "INFO"},
    },
}
