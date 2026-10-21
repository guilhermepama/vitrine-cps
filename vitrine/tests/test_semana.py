"""Critérios de aceite da página /semana-da-tecnologia/ (specs/07-pagina-inicial.md) — guardrail 8."""

import re
from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from cadastro.models import Projeto
from cadastro.tests import fabricas
from vitrine.tests import auxiliares as aux
from vitrine.tests.test_inicio import ROTAS_DE_VOTO, _publicado, _turma

ROTA = "/semana-da-tecnologia/"
MENU = [ROTA + "#mostra", ROTA, "/projetos/", "/grupo/"]


def _html(client, rota=ROTA):
    resposta = client.get(rota)
    assert resposta.status_code == 200
    return resposta.content.decode()


def _menu(html):
    return html[html.index('<nav class="nav"'):html.index("</nav>")]


def test_rota():
    assert reverse("vitrine:semana") == ROTA


@pytest.mark.django_db
def test_titulo_e_atividades(client):
    html = _html(client)
    assert "<title>Semana da Tecnologia — Vitrine Fatec</title>" in html
    for atividade in ("Oficinas e workshops", "Palestras e apresentações", "Conexão Fatec"):
        assert atividade in html
    assert 'href="/projetos/">Ver os projetos' in html  # no item da Mostra


@pytest.mark.django_db
def test_data_e_nome_da_mostra_vem_da_edicao(client):
    fabricas.edicao(ativa=True, nome="2026/2", data_evento=date(2099, 10, 29))
    html = _html(client)
    assert "Edição 2026/2" in html and "em 29 de outubro" in html and "29.10, a partir das 19h" in html


@pytest.mark.django_db
def test_sem_edicao_ativa_nao_mostra_data(client):
    html = _html(client)
    assert "a partir das 19h" not in html and "Edição" not in html


@pytest.mark.django_db
def test_termina_com_o_convite_ao_vestibular(client):
    html = _html(client)
    assert 'href="https://vestibular.fatec.sp.gov.br/"' in html
    assert "Queremos ver seu nome nos próximos projetos" in html


@pytest.mark.django_db
def test_nenhum_caminho_de_voto(client):
    html = _html(client)
    destinos = re.findall(r'(?:href|src|action)="([^"]*)"', html)
    assert destinos and not [d for d in destinos if d.startswith(ROTAS_DE_VOTO)]
    assert "<form" not in html


@pytest.mark.django_db
def test_mostra_sorteia_quatro_projetos_e_chama_para_todos(client):
    edicao = aux.nova_edicao(data_evento=date(2099, 10, 29))
    turma = _turma(edicao, "DSM", 3)
    for i in range(6):
        _publicado(turma, f"Projeto {i:02d}")
    html = _html(client)
    mostra = html[html.index('id="mostra"'):]
    mostra = mostra[:mostra.index("</section>")]
    assert mostra.count('class="cartao-projeto"') == 4
    assert mostra.index('class="cartao-projeto"') < mostra.index('href="/projetos/">Ver todos os 6 projetos')
    assert "A Conexão Fatec é um dos dias da <strong>Semana da Tecnologia</strong>" in mostra


@pytest.mark.django_db
def test_com_ate_quatro_publicados_mostra_todos_sem_o_botao(client):
    edicao = aux.nova_edicao(data_evento=date(2099, 10, 29))
    turma = _turma(edicao, "DSM", 3)
    for i in range(4):
        _publicado(turma, f"Projeto {i:02d}")
    html = _html(client)
    assert html.count('class="cartao-projeto"') == 4
    assert "Ver todos os" not in html


@pytest.mark.django_db
def test_so_publicados_da_edicao_ativa(client):
    edicao = aux.nova_edicao(data_evento=date(2099, 10, 29))
    turma = _turma(edicao, "DSM", 3)
    _publicado(turma, "Visivel")
    oculto = fabricas.projeto(turma, titulo="Oculto em revisão")
    oculto.status = Projeto.Status.EM_REVISAO
    oculto.save()
    _publicado(_turma(aux.nova_edicao(ativa=False, data_evento=date(2026, 5, 1)), "GTUR", 2), "Edicao Antiga")
    html = _html(client)
    assert html.count('class="cartao-projeto"') == 1
    assert "Visivel" in html and "Oculto" not in html and "Edicao Antiga" not in html


@pytest.mark.django_db
def test_sem_projeto_publicado_sem_cartoes_nem_botao(client):
    aux.nova_edicao(data_evento=date(2099, 10, 29))
    html = _html(client)
    assert 'class="cartao-projeto"' not in html and "Ver todos os" not in html


@pytest.mark.django_db
def test_consultas_nao_crescem_com_os_projetos(client):
    edicao = aux.nova_edicao(data_evento=date(2099, 10, 29))
    _publicado(_turma(edicao, "DSM", 3), "Um")
    with CaptureQueriesContext(connection) as poucos:
        _html(client)
    for i in range(6):
        _publicado(_turma(edicao, f"C{i}", 1), f"Mais {i}", integrantes=3)
    with CaptureQueriesContext(connection) as muitos:
        _html(client)
    assert len(muitos) == len(poucos)


@pytest.mark.django_db
def test_menu_marca_a_semana(client):
    menu = _menu(_html(client))
    assert re.findall(r'href="([^"]*)"', menu) == ["#mostra", ROTA, "/projetos/", "/grupo/"]
    assert f'href="{ROTA}" class="so-desktop" aria-current="page"><span class="idx" aria-hidden="true">02</span>Semana da Tecnologia' in menu
    assert re.findall(r'class="idx" aria-hidden="true">(\d+)<', menu) == ["01", "02", "03"]


@pytest.mark.django_db
def test_a_mostra_tem_ancora_na_semana(client):
    html = _html(client)
    secao = html[html.index('id="mostra"'):]
    assert secao.index("02 — Conexão Fatec") < secao.index("</section>")


@pytest.mark.django_db
def test_menus_da_home_e_de_projetos(client):
    menu = _menu(_html(client, "/"))
    assert re.findall(r'href="([^"]*)"', menu) == MENU
    assert "aria-current" not in menu
    menu = _menu(_html(client, "/projetos/"))
    assert re.findall(r'href="([^"]*)"', menu) == MENU
    assert 'href="/projetos/" aria-current="page"' in menu


@pytest.mark.django_db
def test_home_fala_do_vitrine_e_leva_a_semana(client):
    html = _html(client, "/")
    assert html.count(f'href="{ROTA}"') == 3  # menu + texto de "Quem faz" + rodapé (fora o #mostra)
    quem = html[html.index('id="quem-faz"'):html.index('id="projetos"')]
    assert "O <strong>Vitrine Fatec</strong> é o espaço onde a Fatec Olímpia mostra" in quem
    assert "tecnica__cel" not in quem  # os quatro blocos saíram
