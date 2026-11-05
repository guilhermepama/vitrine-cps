"""Caminho crítico do resultado público (spec 09)."""

import re
from decimal import Decimal
from pathlib import Path

import pytest

URL = "/resultado/2026/"
CSS = Path(__file__).resolve().parents[2] / "static" / "css" / "resultado.css"
ROTAS_DE_VOTO = re.compile(r"""(href|action|src)=["'][^"']*/(entrar|estacao|votar|votos|visitantes)""")


def _html(client):
    resposta = client.get(URL)
    assert resposta.status_code == 200
    return resposta.content.decode()


def _numero(texto):
    return Decimal(texto.strip().replace(",", "."))


# --- Rota e acesso -----------------------------------------------------------------


@pytest.mark.django_db
def test_anonimo_ve_o_resultado_sem_consultar_o_banco(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        html = _html(client)
    for vencedor in ("RotaSaúde", "Sabores que Transformam", "ALÉM DOS NÚMEROS"):
        assert vencedor in html
    assert "Como calculamos" in html


@pytest.mark.parametrize("url", ["/resultado/2025/", "/resultado/0/", "/resultado/abc/", "/resultado/-1/"])
@pytest.mark.django_db
def test_ano_sem_resultado_divulgado_ou_invalido_e_404(client, url):
    assert client.get(url).status_code == 404


@pytest.mark.parametrize("metodo", ["post", "put", "delete"])
@pytest.mark.django_db
def test_so_get(client, metodo):
    assert getattr(client, metodo)(URL).status_code == 405


@pytest.mark.django_db
def test_herda_a_identidade_e_nao_tem_caminho_de_voto(client):
    html = _html(client)
    assert "css/base.css" in html and "css/resultado.css" in html
    assert not ROTAS_DE_VOTO.search(html)  # G8


# --- Os números fecham -------------------------------------------------------------


def _linhas(html):
    """(projeto, [pts banca, pts conv, pts público], final) de cada linha dos rankings."""
    linhas = []
    for tr in re.findall(r"(?s)<tr[^>]*>(.*?)</tr>", html):
        if "rp-final" not in tr or "<td" not in tr:
            continue
        nome = re.search(r'rp-proj__nome">([^<]+)<', tr).group(1)
        pontos = [
            Decimal(0) if "rp-nd" in c else _numero(c)
            for c in re.findall(r'<td class="rp-num rp-conta">(.*?)</td>', tr)
        ]
        final = _numero(re.search(r'<td class="rp-num rp-final">([^<]+)</td>', tr).group(1))
        linhas.append((nome, pontos, final))
    return linhas


@pytest.mark.django_db
def test_pontos_de_cada_fonte_somam_a_nota_final(client):
    linhas = _linhas(_html(client))
    assert len(linhas) == 28  # DSM 21 + GTUR 4 + EM 3
    for nome, pontos, final in linhas:
        assert len(pontos) == 3, nome
        assert abs(sum(pontos) - final) <= Decimal("0.02"), nome  # arredondamento de 2 casas em cada parte


@pytest.mark.django_db
def test_ordem_decrescente_e_primeiro_lugar_de_cada_curso(client):
    html = _html(client)
    for curso, primeiro in (("dsm", "RotaSaúde"), ("gtur", "Sabores que Transformam"), ("em", "ALÉM DOS NÚMEROS")):
        secao = re.search(rf'(?s)<section class="rp-curso" id="{curso}".*?</section>', html).group(0)
        linhas = _linhas(secao)
        finais = [final for _, _, final in linhas]
        assert finais == sorted(finais, reverse=True), curso
        assert linhas[0][0].startswith(primeiro), curso


@pytest.mark.django_db
def test_projeto_sem_ficha_aparece_fora_do_ranking_com_o_nome_apresentado(client):
    html = _html(client)
    assert "Fora do ranking" in html
    assert "Trilha Interpretativa da Gruta de São José" in html
    assert "Conhecendo as unidades de conservação do Brasil" in html


# --- CSS: escopo e celular ----------------------------------------------------------


def _regras(css):
    css = re.sub(r"(?s)/\*.*?\*/", "", css)
    regras = []
    for seletor, corpo in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        props = dict((p.strip(), v.strip()) for p, v in (d.split(":", 1) for d in corpo.split(";") if ":" in d))
        regras.append((" ".join(seletor.split()), props))
    return regras


def test_css_so_estiliza_dentro_da_pagina_do_resultado():
    """Nenhuma regra vaza para o resto do site: todo seletor começa em .rp ou .rp-*."""
    for seletor, _ in _regras(CSS.read_text(encoding="utf-8")):
        for parte in seletor.split(","):
            assert re.match(r"\.rp(\b|-)", parte.strip()), parte


def test_css_sem_largura_fixa_acima_de_360px_nem_rolagem_forcada():
    for seletor, props in _regras(CSS.read_text(encoding="utf-8")):
        for nome in ("width", "min-width"):
            px = re.fullmatch(r"(\d+(?:\.\d+)?)px", props.get(nome, ""))
            assert not (px and float(px.group(1)) > 360), (seletor, nome)
        assert props.get("overflow-x") != "scroll", seletor
        assert props.get("overflow-wrap") != "normal", seletor
