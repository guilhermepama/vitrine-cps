"""Páginas do grupo, `/como-votar/` e regras de código do app (specs/02-vitrine-publica.md)."""

import re
from pathlib import Path

import pytest
from django.urls import reverse

PASTA_DO_APP = Path(__file__).resolve().parent.parent


def test_como_votar_tem_nome_de_rota_e_responde_200(client):
    assert reverse("vitrine:como_votar") == "/como-votar/"
    r = client.get("/como-votar/")
    assert r.status_code == 200 and "presencialmente" in r.content.decode()


def test_como_votar_nao_tem_caminho_de_voto(client):
    """Guardrail 8: nenhum link, formulário ou ação aponta para as rotas de voto."""
    html = client.get("/como-votar/").content.decode()
    for destino in re.findall(r'(?:href|action|src)="([^"]*)"', html):
        assert not destino.startswith(("/entrar", "/estacao", "/votar", "/votos", "/visitantes")), destino
    assert "<form" not in html


@pytest.mark.django_db
def test_paginas_do_grupo_tem_os_cabecalhos_de_protecao(client):
    for resposta in (client.get("/grupo/"), client.get("/grupo/editar/naoexiste/")):
        assert resposta["Referrer-Policy"] == "no-referrer"
        assert resposta["X-Robots-Tag"] == "noindex"
        assert "no-store" in resposta["Cache-Control"]


@pytest.mark.django_db
def test_ra_enorme_e_tratado_como_falha_comum(client):
    assert client.post("/grupo/", {"ra": "1" * 5000}).status_code == 400


def test_nenhum_update_em_lote_no_app():
    """Spec 01: status, slug e turma só mudam por save() na instância (nunca update())."""
    for arquivo in PASTA_DO_APP.glob("*.py"):
        codigo = arquivo.read_text(encoding="utf-8")
        assert "bulk_update" not in codigo, arquivo.name
        assert not re.search(r"\.objects[^\n]*\.update\(", codigo), arquivo.name
        assert not re.search(r"\.filter\([^\n]*\)\.update\(", codigo), arquivo.name


def test_o_app_nao_le_o_ip_direto():
    for arquivo in PASTA_DO_APP.glob("*.py"):
        codigo = arquivo.read_text(encoding="utf-8")
        assert "REMOTE_ADDR" not in codigo and "X-Forwarded-For" not in codigo, arquivo.name


def test_o_app_nao_usa_sql_cru():
    """Guardrail 13: só ORM, queries parametrizadas."""
    for arquivo in PASTA_DO_APP.glob("*.py"):
        codigo = arquivo.read_text(encoding="utf-8")
        assert not re.search(r"\.raw\(|\.extra\(|cursor\(|\.execute\(|RawSQL", codigo), arquivo.name
