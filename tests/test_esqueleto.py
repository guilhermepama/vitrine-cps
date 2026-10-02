"""Testes da fundação (specs/00-esqueleto.md)."""

import os

import pytest
from django.conf import settings
from django.core.cache import cache
from django.db import connection

from config.env import carregar_env


@pytest.mark.django_db
def test_saude_responde_ok(client):
    resposta = client.get("/saude/")
    assert resposta.status_code == 200
    assert resposta.content == b"ok"


@pytest.mark.django_db
def test_saude_so_aceita_get(client):
    assert client.post("/saude/").status_code == 405


@pytest.mark.django_db
def test_banco_e_postgres():
    # Guardrail 4 / ADR-002: a unicidade do voto é testada no mesmo banco da produção.
    assert connection.vendor == "postgresql"


@pytest.mark.django_db
def test_admin_exige_login(client):
    # Guardrail 15.
    resposta = client.get("/admin/")
    assert resposta.status_code == 302
    assert "/admin/login/" in resposta["Location"]


@pytest.mark.django_db
def test_tela_de_login_do_admin_abre(client):
    assert client.get("/admin/login/").status_code == 200


@pytest.mark.django_db
def test_cache_e_compartilhado_entre_processos():
    # Guardrail 7: rate limit precisa de contador único para todos os workers.
    assert settings.CACHES["default"]["BACKEND"] == "django.core.cache.backends.db.DatabaseCache"
    cache.set("teste-esqueleto", 1, 30)
    assert cache.get("teste-esqueleto") == 1


def test_carregar_env_nao_sobrescreve_variavel_existente(tmp_path, monkeypatch):
    arquivo = tmp_path / ".env"
    arquivo.write_text(
        "# comentário\nVITRINE_A=do_arquivo\nVITRINE_B=\"com aspas\"\nlinha invalida\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("VITRINE_A", "do_ambiente")
    monkeypatch.delenv("VITRINE_B", raising=False)

    carregar_env(arquivo)

    assert os.environ["VITRINE_A"] == "do_ambiente"
    assert os.environ["VITRINE_B"] == "com aspas"


def test_carregar_env_sem_arquivo_nao_falha(tmp_path):
    carregar_env(tmp_path / "nao-existe.env")
