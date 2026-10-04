"""DJANGO_URL_PUBLICA (ADR-006): base dos links absolutos, como o QR das estações."""

import os
import subprocess
import sys

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from config.env import url_publica


def test_producao_aceita_origem_https_e_tira_a_barra_do_fim():
    assert url_publica("https://vitrine.exemplo.com.br/", debug=False) == "https://vitrine.exemplo.com.br"
    assert url_publica(" https://vitrine.exemplo.com.br ", debug=False) == "https://vitrine.exemplo.com.br"


def test_producao_sem_valor_falha():
    with pytest.raises(ImproperlyConfigured, match="DJANGO_URL_PUBLICA"):
        url_publica("", debug=False)
    with pytest.raises(ImproperlyConfigured, match="DJANGO_URL_PUBLICA"):
        url_publica(None, debug=False)


@pytest.mark.parametrize(
    "valor",
    [
        "http://vitrine.exemplo.com.br",  # sem https em produção
        "vitrine.exemplo.com.br",  # sem esquema
        "ftp://vitrine.exemplo.com.br",
        "https://",
        "https://vitrine.exemplo.com.br/entrar",  # com caminho
        "https://vitrine.exemplo.com.br?x=1",
        "https://vitrine.exemplo.com.br#x",
        "https://usuario:senha@vitrine.exemplo.com.br",
        "https://usuario@vitrine.exemplo.com.br",
    ],
)
def test_producao_recusa_o_que_nao_e_origem_https(valor):
    with pytest.raises(ImproperlyConfigured, match="DJANGO_URL_PUBLICA"):
        url_publica(valor, debug=False)


def test_desenvolvimento_vazio_vira_localhost_e_aceita_http():
    assert url_publica("", debug=True) == "http://localhost:8000"
    assert url_publica("http://127.0.0.1:8000/", debug=True) == "http://127.0.0.1:8000"


def test_desenvolvimento_tambem_recusa_caminho():
    with pytest.raises(ImproperlyConfigured):
        url_publica("http://localhost:8000/entrar", debug=True)


@pytest.mark.parametrize("valor", ["", "http://vitrine.exemplo.com.br"])
def test_aplicacao_nao_sobe_em_producao_sem_url_publica_https(valor):
    # Variável vazia (e não ausente): o .env local não a preenche, porque
    # o carregador nunca sobrescreve o que já existe no ambiente.
    ambiente = dict(
        os.environ,
        DJANGO_SETTINGS_MODULE="config.settings",
        DJANGO_DEBUG="0",
        DJANGO_URL_PUBLICA=valor,
    )
    resultado = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=ambiente, cwd=settings.BASE_DIR, capture_output=True, text=True,
    )
    assert resultado.returncode != 0
    assert "DJANGO_URL_PUBLICA" in resultado.stderr
