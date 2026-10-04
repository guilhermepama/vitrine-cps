"""Leitura do arquivo .env no desenvolvimento local.

Substitui o python-dotenv (fora da lista da ADR-002) com o mínimo:
linhas CHAVE=VALOR, comentários com #, aspas opcionais. Nunca sobrescreve
uma variável que já existe no ambiente.
"""

import os
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def carregar_env(caminho):
    if not caminho.is_file():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave = chave.strip()
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        if chave:
            os.environ.setdefault(chave, valor)


def url_publica(valor, debug):
    """Origem pública do site (ADR-006), normalizada e sem barra no fim.

    Base dos links absolutos que saem do sistema — o QR das estações
    (spec 03) — para não depender do `Host` da requisição nem do
    `X-Forwarded-Proto` do proxy. Só origem: esquema e domínio, sem
    caminho, query, usuário ou senha. Em produção (`debug` falso) é
    obrigatória e com `https://`; no desenvolvimento, vazia vira
    `http://localhost:8000`.
    """
    valor = (valor or "").strip().rstrip("/")
    if not valor:
        if debug:
            return "http://localhost:8000"
        raise ImproperlyConfigured(
            "Variável de ambiente DJANGO_URL_PUBLICA não definida (ver .env.example)."
        )
    partes = urlsplit(valor)
    esquemas = {"https", "http"} if debug else {"https"}
    if (
        partes.scheme not in esquemas
        or not partes.hostname
        or partes.username is not None
        or partes.password is not None
        or partes.path
        or partes.query
        or partes.fragment
    ):
        raise ImproperlyConfigured(
            "DJANGO_URL_PUBLICA inválida: use só a origem, ex.: "
            "https://vitrine.exemplo.com.br (https:// obrigatório em produção)."
        )
    return valor
