"""Critérios de aceite da página de projetos /projetos/ (specs/07-pagina-inicial.md) — guardrail 8."""

import re
from datetime import date, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from cadastro.models import Curso, Projeto
from cadastro.tests import fabricas
from vitrine.tests import auxiliares as aux
from vitrine.tests.test_inicio import ROTAS_DE_VOTO, _publicado, _turma


def _html(client):
    resposta = client.get("/projetos/")
    assert resposta.status_code == 200
    return resposta.content.decode()


@pytest.fixture
def edicao():
    return aux.nova_edicao(data_evento=timezone.localdate() + timedelta(days=10))


def test_rota():
    assert reverse("vitrine:projetos") == "/projetos/"


@pytest.mark.django_db
def test_titulo_da_pagina(client):
    assert "<title>Projetos — Vitrine Fatec</title>" in _html(client)


@pytest.mark.django_db
def test_lista_todos_os_publicados_da_edicao_ativa(client, edicao):
    turma = _turma(edicao, "DSM", 3)
    for i in range(7):
        _publicado(turma, f"Projeto {i:02d}")
    oculto = fabricas.projeto(turma, titulo="Oculto em revisão")
    oculto.status = Projeto.Status.EM_REVISAO
    oculto.save()
    _publicado(_turma(aux.nova_edicao(ativa=False, data_evento=date(2026, 5, 1)), "GTUR", 2), "Edicao Antiga")

    html = _html(client)
    assert html.count('class="cartao-projeto"') == 7
    assert "Sete projetos, uma turma" in html
    assert "Oculto" not in html and "Edicao Antiga" not in html


@pytest.mark.django_db
def test_ordem_das_turmas_e_dos_projetos(client, edicao):
    etec = _turma(edicao, "ADM", 2, unidade=Curso.Unidade.ETEC, tipo="ano")
    dsm2 = _turma(edicao, "DSM", 2)
    gtur3 = _turma(edicao, "GTUR", 3)
    dsm3 = _turma(edicao, "DSM", 3)
    _publicado(etec, "Recicla")
    _publicado(dsm2, "Cantina")
    _publicado(gtur3, "Olimpia 360")
    _publicado(dsm3, "Zeta")
    _publicado(dsm3, "Alfa")

    html = _html(client)
    posicoes = [html.index(t) for t in ("Alfa", "Zeta", "Cantina", "Olimpia 360", "Recicla")]
    assert posicoes == sorted(posicoes)


@pytest.mark.django_db
def test_cartao_igual_ao_da_home(client, edicao):
    p = _publicado(_turma(edicao, "DSM", 3), "Fila Zero", integrantes=4, link_repositorio="https://github.com/x/y")
    html = _html(client)
    assert f'href="/projeto/{p.slug}/"' in html
    assert "4 integrantes" in html and "Repositório" in html and "DSM · 3º sem" in html


@pytest.mark.django_db
def test_filtro_tem_um_chip_por_curso_e_vem_escondido(client, edicao):
    _publicado(_turma(edicao, "DSM", 3), "A")
    _publicado(_turma(edicao, "GTUR", 2), "B")
    html = _html(client)
    assert re.search(r'<div class="filtros"[^>]*data-filtro-cursos hidden>', html)
    assert re.findall(r'class="chip[^"]*" data-curso="([^"]+)"', html) == ["todos", "dsm", "gtur"]
    assert 'data-curso="dsm">' in html
    assert "js/filtro-cursos.js" in html


@pytest.mark.django_db
def test_sem_edicao_ativa(client):
    html = _html(client)
    assert "aparecem aqui assim que a coordenação publicar" in html
    assert "Projetos em breve" in html and "data-filtro-cursos" not in html


@pytest.mark.django_db
def test_nenhum_caminho_de_voto(client, edicao):
    _publicado(_turma(edicao, "DSM", 3), "Fila Zero")
    html = _html(client)
    destinos = re.findall(r'(?:href|src|action)="([^"]*)"', html)
    assert destinos and not [d for d in destinos if d.startswith(ROTAS_DE_VOTO)]
    assert "<form" not in html


@pytest.mark.django_db
def test_sem_dado_pessoal(client, edicao):
    p = _publicado(_turma(edicao, "DSM", 3), "Fila Zero", integrantes=2, representante_nome="Representante Secreta")
    html = _html(client)
    assert "Representante Secreta" not in html and "Pessoa0" not in html and p.ra_hmac not in html


@pytest.mark.django_db
def test_consultas_nao_crescem_com_os_projetos(client, edicao):
    _publicado(_turma(edicao, "DSM", 3), "Um")
    with CaptureQueriesContext(connection) as poucos:
        _html(client)
    for i in range(6):
        _publicado(_turma(edicao, f"C{i}", 1), f"Mais {i}", integrantes=3)
    with CaptureQueriesContext(connection) as muitos:
        _html(client)
    assert len(muitos) == len(poucos)
