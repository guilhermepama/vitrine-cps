"""Critérios de aceite da página inicial (specs/07-pagina-inicial.md) — guardrail 8."""

import re
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.staticfiles import finders
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from cadastro.models import Curso, Edicao, Integrante, Projeto
from cadastro.tests import fabricas
from vitrine import inicio
from vitrine.tests import auxiliares as aux

ROTAS_DE_VOTO = ("/entrar", "/estacao", "/votar", "/votos", "/visitantes")


def _publicado(turma, titulo, integrantes=1, **campos):
    projeto = fabricas.projeto(turma, titulo=titulo, resumo=f"Resumo de {titulo}.", descricao="Descrição.", **campos)
    for ordem in range(integrantes):
        Integrante.objects.create(projeto=projeto, nome=f"Pessoa{ordem} Sobrenome", ordem=ordem)
    aux.com_capa(projeto)
    projeto.status = Projeto.Status.EM_REVISAO
    projeto.save(update_fields=["status", "atualizado_em"])
    assert projeto.publicar() == []
    return Projeto.objects.get(pk=projeto.pk)


def _turma(edicao, sigla, periodo, unidade=Curso.Unidade.FATEC, tipo="semestre"):
    curso = Curso.objects.filter(sigla=sigla).first() or fabricas.curso(sigla=sigla, unidade=unidade)
    return fabricas.turma(edicao, curso, numero_periodo=periodo, tipo_periodo=tipo)


def _html(client):
    resposta = client.get("/")
    assert resposta.status_code == 200
    return resposta.content.decode()


@pytest.fixture
def edicao():
    return aux.nova_edicao(data_evento=timezone.localdate() + timedelta(days=10))


# --- Rota e título -------------------------------------------------------------------


def test_rota_inicio_e_a_raiz():
    assert reverse("vitrine:inicio") == "/"


@pytest.mark.django_db
def test_titulo_da_pagina(client):
    assert "<title>Vitrine CPS — Mostra de Projetos Fatec Olímpia</title>" in _html(client)


# --- O que aparece ---------------------------------------------------------------------


@pytest.mark.django_db
def test_so_publicados_da_edicao_ativa(client, edicao):
    turma = _turma(edicao, "DSM", 3)
    _publicado(turma, "Fila Zero")
    for status in (Projeto.Status.PRE_CADASTRADO, Projeto.Status.EM_REVISAO, Projeto.Status.AJUSTES):
        p = fabricas.projeto(turma, titulo=f"Oculto {status}")
        p.status = status
        p.save()
    outra = aux.nova_edicao(ativa=False, data_evento=date(2026, 5, 1))
    _publicado(_turma(outra, "GTUR", 2), "Edicao Antiga")

    html = _html(client)
    assert "Fila Zero" in html
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
def test_cartao_leva_a_pagina_do_projeto_e_resume_os_links(client, edicao):
    p = _publicado(_turma(edicao, "DSM", 3), "Fila Zero", integrantes=4, link_repositorio="https://github.com/x/y", link_video="https://youtu.be/z")
    html = _html(client)
    assert f'href="/projeto/{p.slug}/"' in html
    assert "4 integrantes" in html and "Repositório · vídeo" in html and "DSM · 3º sem" in html
    assert f'src="{p.capa.url}"' in html


def test_resumo_dos_links_sem_nenhum():
    assert inicio.links_do_projeto(Projeto(titulo="x")) == "—"
    assert inicio.links_do_projeto(Projeto(link_demo="https://a.b")) == "Demo"


@pytest.mark.parametrize(
    ("n", "singular", "plural", "feminino", "esperado"),
    [
        (1, "projeto", "projetos", False, "um projeto"),
        (8, "projeto", "projetos", False, "oito projetos"),
        (1, "turma", "turmas", True, "uma turma"),
        (2, "turma", "turmas", True, "duas turmas"),
        (20, "turma", "turmas", True, "vinte turmas"),
        (23, "projeto", "projetos", False, "23 projetos"),
    ],
)
def test_contagem_por_extenso(n, singular, plural, feminino, esperado):
    assert inicio.contagem(n, singular, plural, feminino) == esperado


@pytest.mark.django_db
def test_titulo_da_secao_conta_projetos_e_turmas(client, edicao):
    dsm = _turma(edicao, "DSM", 3)
    _publicado(dsm, "A")
    _publicado(dsm, "B")
    _publicado(_turma(edicao, "GTUR", 2), "C")
    assert "Três projetos, duas turmas" in _html(client)


@pytest.mark.django_db
def test_filtro_tem_um_chip_por_curso_e_vem_escondido(client, edicao):
    _publicado(_turma(edicao, "DSM", 3), "A")
    _publicado(_turma(edicao, "GTUR", 2), "B")
    html = _html(client)
    assert re.search(r'<div class="filtros"[^>]*data-filtro-cursos hidden>', html)
    assert re.findall(r'class="chip[^"]*" data-curso="([^"]+)"', html) == ["todos", "dsm", "gtur"]
    assert 'data-curso="dsm">' in html  # turma marcada para o filtro
    assert "js/filtro-cursos.js" in html


# --- Sem edição, sem projeto, depois do evento ------------------------------------------


@pytest.mark.django_db
def test_sem_edicao_ativa(client):
    html = _html(client)
    assert "aparecem aqui assim que a coordenação publicar" in html
    assert "Dados do evento" not in html and "Premiação" not in html and "data-filtro-cursos" not in html


@pytest.mark.django_db
def test_edicao_sem_projeto_publicado(client, edicao):
    fabricas.projeto(_turma(edicao, "DSM", 3), titulo="Ainda em cadastro")
    html = _html(client)
    assert "aparecem aqui assim que a coordenação publicar" in html
    assert "Projetos em breve" in html and "data-filtro-cursos" not in html


@pytest.mark.django_db
def test_data_nome_e_pesos_vem_da_edicao(client):
    fabricas.edicao(ativa=True, nome="2026/2", data_evento=date(2099, 10, 29), peso_banca=Decimal("0.60"), peso_publico=Decimal("0.40"))
    html = _html(client)
    assert "Edição 2026/2" in html
    assert '29<span class="ponto">.</span>10' in html
    assert "Quinta-feira, 29 de outubro" in html and "a partir das 19h" in html
    assert "banca (60%) + público (40%)" in html


@pytest.mark.django_db
def test_depois_do_evento_vira_realizada_em(client):
    aux.nova_edicao(data_evento=timezone.localdate() - timedelta(days=1))
    html = _html(client)
    assert "Realizada em" in html and "a partir das 19h" not in html


@pytest.mark.django_db
def test_chamada_da_fatec_leva_aos_sites_oficiais(client):
    html = _html(client)
    assert 'href="https://fatecolimpia.cps.sp.gov.br/"' in html
    assert 'href="https://vestibular.fatec.sp.gov.br/"' in html
    assert "Queremos ver seu nome nos próximos projetos" in html
    assert html.index("vestibular.fatec.sp.gov.br") < html.index('href="https://fatecolimpia.cps.sp.gov.br/" rel="noopener noreferrer">Conheça')


# --- Guardrails ------------------------------------------------------------------------


@pytest.mark.django_db
def test_nenhum_caminho_de_voto(client, edicao):
    """G8: nenhum href, src ou action da home leva às rotas do voto."""
    _publicado(_turma(edicao, "DSM", 3), "Fila Zero")
    html = _html(client)
    destinos = re.findall(r'(?:href|src|action)="([^"]*)"', html)
    assert destinos and not [d for d in destinos if d.startswith(ROTAS_DE_VOTO)]
    assert "<form" not in html
    assert 'href="/grupo/"' in html and 'href="/como-votar/"' in html


@pytest.mark.django_db
def test_sem_dado_pessoal(client, edicao):
    p = _publicado(_turma(edicao, "DSM", 3), "Fila Zero", integrantes=2, representante_nome="Representante Secreta")
    html = _html(client)
    assert "Representante Secreta" not in html and "Pessoa0" not in html and p.ra_hmac not in html


@pytest.mark.django_db
def test_consultas_nao_crescem_com_os_projetos(client, edicao):
    dsm = _turma(edicao, "DSM", 3)
    _publicado(dsm, "Um")
    with CaptureQueriesContext(connection) as poucos:
        _html(client)
    for i in range(6):
        _publicado(_turma(edicao, f"C{i}", 1), f"Mais {i}", integrantes=3)
    with CaptureQueriesContext(connection) as muitos:
        _html(client)
    assert len(muitos) == len(poucos)


@pytest.mark.django_db
def test_sem_fontes_externas_e_sem_largura_fixa(client, edicao):
    _publicado(_turma(edicao, "DSM", 3), "Fila Zero")
    html = _html(client)
    assert "fonts.googleapis" not in html and "fonts.gstatic" not in html
    # Dentro do <svg> os números são coordenadas do viewBox, não largura de layout.
    fora_do_svg = re.sub(r"(?s)<svg\b.*?</svg>", "", html)
    for largura in re.findall(r'\swidth="(\d+)"', fora_do_svg):
        assert int(largura) <= 360


def test_css_sem_url_do_google():
    """Spec 07: fontes servidas de static/fonts/; nenhuma URL do Google no CSS."""
    with open(finders.find("css/base.css"), encoding="utf-8") as arquivo:
        css = arquivo.read()
    assert "googleapis" not in css and "gstatic" not in css
