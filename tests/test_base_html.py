"""`templates/base.html` do projeto (spec 02, "Dependências do coordenador").

As páginas das specs herdam este arquivo pelos blocos `titulo`, `meta` e
`conteudo`. A identidade visual entra depois sem mudar o nome nem os blocos.
"""

import re

from django.contrib.staticfiles import finders
from django.template import engines

FILHO = (
    '{% extends "base.html" %}'
    "{% block titulo %}Projeto X — Vitrine CPS{% endblock %}"
    '{% block meta %}<meta property="og:title" content="Projeto X">{% endblock %}'
    "{% block conteudo %}<p>corpo</p>{% endblock %}"
)


def test_blocos_titulo_meta_e_conteudo():
    html = engines["django"].from_string(FILHO).render()
    assert "<title>Projeto X — Vitrine CPS</title>" in html
    assert '<meta property="og:title" content="Projeto X">' in html
    assert "<p>corpo</p>" in html
    assert '<html lang="pt-BR">' in html
    assert 'name="viewport"' in html


def test_titulo_padrao():
    html = engines["django"].from_string('{% extends "base.html" %}').render()
    assert "<title>Vitrine CPS</title>" in html


def _pagina(filho='{% extends "base.html" %}'):
    return engines["django"].from_string(filho).render()


def test_carrega_o_css_da_identidade():
    assert '<link rel="stylesheet" href="/static/css/base.css">' in _pagina()
    assert finders.find("css/base.css"), "static/css/base.css precisa ser achado pelo staticfiles"


def test_meta_vem_depois_do_css_base():
    """O CSS de um app (bloco meta) entra depois do base.css e pode sobrescrevê-lo."""
    html = engines["django"].from_string(FILHO).render()
    assert html.index("css/base.css") < html.index('property="og:title"')


ROTAS_DE_VOTO = ("/entrar", "/estacao", "/votar", "/votos", "/visitantes")


def test_cabecalho_e_rodape_sem_caminho_de_voto_nem_formulario():
    """G8: o esqueleto comum só leva à página inicial e à área do grupo (nem à explicação do voto,
    que a página de um projeto de edição passada não pode oferecer — spec 02)."""
    html = _pagina()
    assert "<form" not in html
    destinos = re.findall(r'(?:href|src|action)="([^"]*)"', html)
    assert not [d for d in destinos if d.startswith(ROTAS_DE_VOTO)]
    assert "/como-votar/" not in destinos
    assert {"/", "/grupo/"} <= set(destinos)


def test_menu_vazio_por_padrao():
    """Spec 07: cada página decide o próprio menu; o esqueleto só tem a marca."""
    html = _pagina()
    assert 'class="nav' not in html and "<script" not in html


def test_cabecalho_e_rodape_nao_saem_na_impressao():
    """A ficha da banca herda base.html: o cabeçalho não pode ir para o papel."""
    html = _pagina()
    assert re.search(r'<header class="[^"]*nao-imprime', html)
    assert re.search(r'<footer class="[^"]*nao-imprime', html)


def test_cabecalho_e_rodape_podem_ser_trocados():
    html = _pagina('{% extends "base.html" %}{% block topo %}{% endblock %}{% block rodape %}{% endblock %}')
    assert "<header" not in html and "<footer" not in html


def test_pagina_pode_tirar_o_layout_do_main():
    """A ficha da banca controla a própria paginação e zera as classes do <main>."""
    assert "<main class=\"\">" in _pagina('{% extends "base.html" %}{% block classe_main %}{% endblock %}')


def _css_base():
    with open(finders.find("css/base.css"), encoding="utf-8") as arquivo:
        return arquivo.read()


def test_capa_em_banner_recortada_sem_distorcer():
    """Spec 02: capa recortada em banner na proporção do Open Graph."""
    regra = re.search(r"\.banner\s*\{([^}]*)\}", _css_base())
    assert regra, ".banner precisa estar no base.css"
    for declaracao in ("width: 100%", "aspect-ratio: 1.91 / 1", "object-fit: cover"):
        assert declaracao in regra.group(1)


def test_imagem_e_texto_longo_cabem_em_360px():
    css = _css_base()
    img = re.search(r"(?m)^img\s*\{([^}]*)\}", css).group(1)
    assert "max-width: 100%" in img and "height: auto" in img
    assert "overflow-wrap: break-word" in re.search(r"(?m)^body\s*\{([^}]*)\}", css).group(1)


def _regras_css(css):
    """Pares (seletor, declarações) de cada regra, inclusive dentro de @media."""
    sem_comentarios = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(sel.strip(), decl) for sel, decl in re.findall(r"([^{}]+)\{([^{}]*)\}", sem_comentarios)]


def test_foco_de_teclado_segue_a_cor_da_superficie():
    """Revisão do #73: o contorno de foco usa --cor-foco, e toda superfície vermelha a redefine.

    Assim qualquer componente novo em fundo vermelho (ex.: .convite, botões da cédula) só
    precisa declarar `--cor-foco: var(--cor-acento-texto)` — sem lista de exceções no seletor global.
    """
    regras = _regras_css(_css_base())
    raiz = next(decl for sel, decl in regras if sel == ":root")  # o primeiro :root (o segundo só muda --gutter)
    assert "--cor-foco: var(--cor-acento)" in raiz
    foco = next(decl for sel, decl in regras if sel == ":focus-visible")
    assert "outline: 3px solid var(--cor-foco)" in foco and "--cor-acento" not in foco
    # Nenhuma exceção de cor por seletor: o foco sobre vermelho é resolvido pela variável.
    # Um seletor pode delegar o foco a outro elemento (ex.: campo oculto + card),
    # desde que use a mesma variável.
    assert not [
        sel for sel, decl in regras
        if ":focus-visible" in sel and sel != ":focus-visible" and "var(--cor-foco)" not in decl
    ]

    vermelhas, brancas = [], []
    for seletor, declaracoes in regras:
        if "::" in seletor:  # pseudoelemento decorativo não recebe foco (ex.: .marca::before)
            continue
        if re.search(r"background(-color)?: var\(--cor-acento\)", declaracoes):
            vermelhas.append(seletor)
            assert "--cor-foco: var(--cor-acento-texto)" in declaracoes, seletor
        if re.search(r"background(-color)?: var\(--cor-acento-texto\)", declaracoes):
            brancas.append(seletor)  # branco dentro do vermelho: o foco volta ao vermelho
            assert "--cor-foco: var(--cor-acento)" in declaracoes, seletor
    assert {".marca", ".botao--vermelho", ".chip--ativo", ".chamada", ".faixa--vermelha"} <= set(vermelhas)
    assert ".chamada .botao--vazado:hover" in brancas
