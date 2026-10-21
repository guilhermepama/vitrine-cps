"""Cédula GET /votar — fatia F6 (specs/03-credenciamento-votacao.md).

Critérios de aceite fechados aqui (citados em cada bloco):
- Cédula: só projetos `publicado` da edição em votação, agrupados por turma;
  votados marcados e desabilitados.
- "`GET /votar` sem token, com token malformado, inexistente ou de outra
  edição → redirect para `/como-votar/`" (G8).
- Liberação: token sem cadastro → formulário; formulário inválido não
  libera; cadastro adulterado ou do ensaio → formulário; cadastro válido →
  cédula; consentimento ausente → `/votar` não libera.
- Isolamento: votos do ensaio não aparecem na cédula do evento (e vice-versa).
- Sem edição em votação: só o aviso "Votação encerrada".
"""

import re
import unittest
import uuid

import pytest
from django.core.signing import Signer
from django.test import Client
from django.urls import clear_url_caches, resolve

from vitrine.views import como_votar
from votacao.cookie_token import COOKIE_TOKEN
from votacao.liberacao import COOKIE_CADASTRO
from votacao.models import Visitante, Voto
from votacao.servicos import abrir_votacao, encerrar_votacao
from votacao.tests import fabricas
from votacao.tests.cenario import montar
from votacao.views_voto import ROTA_COMO_VOTAR

pytestmark = pytest.mark.django_db

ROTA = "/votar"
DESABILITADO = re.compile(r'<button type="button" id="e-\d+" aria-labelledby="e-\d+ p-\d+-titulo" disabled>Avaliado</button>')
CRITERIOS = {"impacto_social": "Impacto social", "inovacao": "Inovação", "impacto_ambiental": "Impacto ambiental"}


@pytest.fixture
def cenario():
    return montar()


def _redirect(resposta, destino):
    assert resposta.status_code == 302
    assert resposta["Location"] == destino
    assert b"Votar" not in resposta.content


def test_cedula_lista_so_publicados_da_edicao_em_votacao_por_turma(client, cenario):
    resposta = cenario.votante(client).get(ROTA)
    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "Agenda Escolar" in html and "Horta Viva" in html
    assert "Rascunho Oculto" not in html and "Projeto do Ensaio" not in html
    # Agrupado por turma (a categoria), com o rótulo da turma como título.
    assert html.count("<h2>") == 2
    assert html.index("ADS — 3º semestre") < html.index("Horta Viva") < html.index("DSM — 3º semestre")
    assert html.index("DSM — 3º semestre") < html.index("Agenda Escolar")
    assert f'data-projeto="{cenario.publicado.pk}"' in html
    assert "no-store" in resposta["Cache-Control"]


def _bloco_do_projeto(html, projeto):
    """O <form> do projeto não avaliado (do <li> que traz o seu data-projeto)."""
    inicio = html.rindex("<form", 0, html.index(f'data-projeto="{projeto.pk}"'))
    return html[inicio : html.index("</form>", inicio)]


def test_cedula_tem_tres_fieldsets_e_dezoito_radios_sem_marcacao_por_projeto(client, cenario):
    html = cenario.votante(client).get(ROTA).content.decode()
    bloco = _bloco_do_projeto(html, cenario.publicado)
    assert bloco.count("<fieldset") == 3
    for campo, rotulo in CRITERIOS.items():
        assert f"<legend>{rotulo}</legend>" in bloco
        for nota in range(6):
            assert re.search(rf'<input type="radio" name="{campo}" id="n-{cenario.publicado.pk}-{campo}-{nota}" value="{nota}">', bloco)
            assert f'<label for="n-{cenario.publicado.pk}-{campo}-{nota}">{nota}</label>' in bloco
    assert bloco.count('type="radio"') == 18
    assert "checked" not in html
    pk = cenario.publicado.pk
    assert f'<button type="button" id="e-{pk}" aria-labelledby="e-{pk} p-{pk}-titulo" data-projeto="{pk}">Enviar avaliação</button>' in bloco
    assert "<title>Avaliação — Vitrine CPS</title>" in html and "Avalie os projetos" in html


def test_projeto_avaliado_nao_tem_controle_que_envie(client, cenario):
    fabricas.voto(cenario.token, cenario.publicado)
    html = cenario.votante(client).get(ROTA).content.decode()
    assert html.count("<form") == 1  # só o outro projeto
    assert f"n-{cenario.publicado.pk}-" not in html
    assert "Enviar avaliação" in html and len(DESABILITADO.findall(html)) == 1


def test_payload_montado_so_com_o_html_da_interface_e_aceito_por_post_votos(client, cenario):
    """Achado da revisão da fase 1: nome errado no template quebra aqui."""
    html = cenario.votante(client).get(ROTA).content.decode()
    bloco = _bloco_do_projeto(html, cenario.publicado)
    dados = {"projeto_id": re.search(r'data-projeto="(\d+)"', bloco)[1]}
    for nome in dict.fromkeys(re.findall(r'<input type="radio" name="([^"]+)"', bloco)):
        dados[nome] = re.search(rf'name="{nome}"[^>]*value="(\d)"', bloco)[1]
    assert set(dados) == {"projeto_id", *CRITERIOS}
    resposta = client.post("/votos", dados)
    assert resposta.status_code == 201
    voto = Voto.objects.get()
    assert (voto.projeto_id, voto.impacto_social, voto.inovacao, voto.impacto_ambiental) == (cenario.publicado.pk, 0, 0, 0)


def test_js_confere_as_tres_notas_antes_do_fetch_e_monta_o_corpo(client, cenario):
    html = cenario.votante(client).get(ROTA).content.decode()
    js = html[html.index("<script>") : html.index("</script>")]
    assert js.index("completo") < js.index("fetch(")
    assert 'var campos = ["impacto_social", "inovacao", "impacto_ambiental"]' in js
    assert "Escolha uma nota em cada critério." in js and "alert(" not in js
    assert "new URLSearchParams(dados)" in js and "projeto_id: botao.dataset.projeto" in js
    assert "Não foi possível enviar a avaliação agora. Tente de novo." in js


def test_js_marca_avaliado_so_no_201_e_recarrega_no_409_e_no_403(client, cenario):
    """No 409 o botão não vira "Avaliado": a rejeição é genérica e pode ser
    cookie vencido, sem voto gravado. No 403 (CSRF, cookies limpos com a
    cédula aberta) também recarrega, em vez de prender o visitante no
    "Tente de novo" (parecer do #36). Recarregar mostra o estado do servidor."""
    html = cenario.votante(client).get(ROTA).content.decode()
    js = html[html.index("<script>") : html.index("</script>")]
    ramo_201 = js[js.index("resposta.status === 201") : js.index("resposta.status === 409")]
    ramo_recarga = js[js.index("resposta.status === 409") :]
    condicao = ramo_recarga[: ramo_recarga.index("{")]
    assert "marcar(botao)" in ramo_201
    assert "resposta.status === 403" in condicao
    assert "location.reload()" in ramo_recarga[: ramo_recarga.index("return;")]
    assert "marcar(" not in ramo_recarga[: ramo_recarga.index("return;")]


def test_cookies_limpos_com_a_cedula_aberta_dao_403_e_a_recarga_sai_da_cedula(cenario):
    """O caminho que o JS percorre no 403: sem cookies, o POST cai no CSRF e o
    GET da recarga leva para /como-votar/ (sem token), sem voto gravado."""
    votante = cenario.votante(Client(enforce_csrf_checks=True))
    html = votante.get(ROTA).content.decode()
    csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
    assert csrf, "a cédula perdeu o csrfmiddlewaretoken"
    votante.cookies.clear()
    dados = {"projeto_id": cenario.publicado.pk, "impacto_social": 4, "inovacao": 2, "impacto_ambiental": 5}
    assert votante.post("/votos", dados, HTTP_X_CSRFTOKEN=csrf[1]).status_code == 403
    recarga = votante.get(ROTA)
    assert recarga.status_code == 302 and recarga["Location"] == str(ROTA_COMO_VOTAR)
    assert not Voto.objects.exists()


def test_cedula_nao_gera_log_de_template_nem_em_debug(client, cenario):
    """Variável ausente no template vira log DEBUG de django.template com o
    contexto inteiro (inclusive os votos do token) — P2."""
    fabricas.voto(cenario.token, cenario.publicado)
    with unittest.TestCase().assertNoLogs("django.template", level="DEBUG"):
        assert cenario.votante(client).get(ROTA).status_code == 200


def test_projeto_avaliado_aparece_marcado_e_desabilitado(client, cenario):
    fabricas.voto(cenario.token, cenario.publicado)
    html = cenario.votante(client).get(ROTA).content.decode()
    assert f'data-projeto="{cenario.publicado.pk}"' not in html
    assert DESABILITADO.search(html)
    assert f'data-projeto="{cenario.outro_publicado.pk}"' in html


def test_votos_do_ensaio_nao_aparecem_no_evento_e_vice_versa(client, cenario):
    # Mesmo projeto do evento votado por um token do ensaio (cenário forçado no banco).
    fabricas.voto(cenario.token_ensaio, cenario.publicado)
    html = cenario.votante(client).get(ROTA).content.decode()
    assert f'data-projeto="{cenario.publicado.pk}"' in html
    assert not DESABILITADO.search(html)

    fabricas.voto(cenario.token, cenario.do_ensaio)
    encerrar_votacao(cenario.evento.pk)
    assert abrir_votacao(cenario.ensaio.pk) is None
    html = cenario.votante(client, cenario.token_ensaio, cadastro_de=cenario.ensaio).get(ROTA).content.decode()
    assert f'data-projeto="{cenario.do_ensaio.pk}"' in html
    assert not DESABILITADO.search(html) and "Horta Viva" not in html


@pytest.mark.parametrize(
    "valor",
    [None, "abc", uuid.uuid4().hex, str(uuid.uuid4()) + "0", str(uuid.uuid4()).upper(), str(uuid.uuid4())],
)
def test_sem_token_valido_vai_para_como_votar(client, cenario, valor):
    cenario.votante(client)
    if valor is None:
        del client.cookies[COOKIE_TOKEN]
    else:
        client.cookies[COOKIE_TOKEN] = valor
    _redirect(client.get(ROTA), str(ROTA_COMO_VOTAR))


def test_token_de_outra_edicao_vai_para_como_votar(client, cenario):
    _redirect(cenario.votante(client, cenario.token_ensaio).get(ROTA), str(ROTA_COMO_VOTAR))


def test_caminho_da_instrucao_e_o_da_spec():
    assert str(ROTA_COMO_VOTAR) == "/como-votar/"
    assert resolve("/como-votar/").func is como_votar


def test_redirect_sem_token_leva_a_pagina_do_vitrine(client, cenario):
    resposta = client.get(ROTA, follow=True)
    assert resposta.redirect_chain == [(str(ROTA_COMO_VOTAR), 302)]
    assert resposta.status_code == 200


def test_token_recem_emitido_sem_cadastro_vai_para_o_formulario(client, cenario):
    cenario.votante(client)
    del client.cookies[COOKIE_CADASTRO]
    _redirect(client.get(ROTA), "/visitantes")


@pytest.mark.parametrize("caso", ["ensaio", "assinatura falsa", "outro salt", "sem assinatura"])
def test_cadastro_adulterado_ou_do_ensaio_vai_para_o_formulario(client, cenario, caso):
    cenario.votante(client)
    evento = str(cenario.evento.pk)
    client.cookies[COOKIE_CADASTRO] = {
        "ensaio": Signer(salt="votacao.cadastro").sign(str(cenario.ensaio.pk)),
        "assinatura falsa": f"{evento}:{'x' * 27}",
        "outro salt": Signer(salt="outro").sign(evento),
        "sem assinatura": evento,
    }[caso]
    _redirect(client.get(ROTA), "/visitantes")


@pytest.mark.parametrize("dados", [{"nome": "A"}, {"consentimento": ""}])
def test_formulario_invalido_nao_libera_a_cedula(client, cenario, dados):
    cenario.votante(client)
    del client.cookies[COOKIE_CADASTRO]
    envio = {"nome": "Ana Souza", "email": "ana@example.com", "telefone": "", "consentimento": "on", **dados}
    assert client.post("/visitantes", envio).status_code == 400
    _redirect(client.get(ROTA), "/visitantes")


def test_cadastro_valido_libera_a_cedula_e_rescan_vai_direto(client, cenario):
    cenario.votante(client)
    del client.cookies[COOKIE_CADASTRO]
    envio = {"nome": "Ana Souza", "email": "ana@example.com", "telefone": "", "consentimento": "on"}
    assert client.post("/visitantes", envio)["Location"] == ROTA
    assert client.get(ROTA).status_code == 200
    # Re-scan com cadastro válido: /visitantes manda direto à cédula, sem novo registro.
    assert client.get("/visitantes")["Location"] == ROTA
    assert Visitante.objects.count() == 1


def test_sem_edicao_em_votacao_mostra_so_o_aviso(client, cenario):
    encerrar_votacao(cenario.evento.pk)
    resposta = cenario.votante(client).get(ROTA)
    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "Votação encerrada" in html
    assert "Agenda Escolar" not in html and "data-projeto" not in html and "csrfmiddlewaretoken" not in html


def test_votacao_encerrada_sem_token_vai_para_como_votar(client, cenario):
    encerrar_votacao(cenario.evento.pk)
    _redirect(client.get(ROTA), str(ROTA_COMO_VOTAR))


def test_so_get(client, cenario):
    assert cenario.votante(client).post(ROTA).status_code == 405


def test_redirect_usa_a_rota_nomeada_e_nao_um_caminho_fixo(client, cenario, settings):
    """Com `vitrine:como_votar` montada em /ajuda/como-votar/, o redirect
    acompanha; uma constante "/como-votar/" fixa falharia aqui."""
    settings.ROOT_URLCONF = "votacao.tests.urls_como_votar_alt"
    clear_url_caches()
    try:
        resposta = client.get(ROTA)
        assert resposta.status_code == 302
        assert resposta["Location"] == "/ajuda/como-votar/"
        assert client.get(resposta["Location"]).status_code == 200
    finally:
        clear_url_caches()


def _elemento_por_id(html, id_):
    """Texto do elemento com esse id (até o próximo fechamento de tag), ou None."""
    achados = re.findall(rf'<(\w+)[^>]*\sid="{re.escape(id_)}"[^>]*>(.*?)</\1>', html, re.S)
    return achados[0][1] if achados else None


def _tag_com(html, trecho):
    padrao = rf"{re.escape(trecho)}[^>]*>" if trecho.startswith("<") else rf"<[^>]*{re.escape(trecho)}[^>]*>"
    return re.search(padrao, html)[0]


def test_form_e_botoes_tem_nome_acessivel_com_o_titulo_do_projeto(client, cenario):
    fabricas.voto(cenario.token, cenario.outro_publicado)
    html = cenario.votante(client).get(ROTA).content.decode()
    # Não avaliado: o form e o botão "Enviar avaliação".
    pk, titulo = cenario.publicado.pk, cenario.publicado.titulo
    form = _tag_com(html, "<form")
    ref = re.search(r'aria-labelledby="([^"]+)"', form)[1]
    assert _elemento_por_id(html, ref) == titulo == _elemento_por_id(html, f"p-{pk}-titulo")
    botao = _tag_com(html, f'data-projeto="{pk}"')
    ids = re.search(r'aria-labelledby="([^"]+)"', botao)[1].split()
    assert ids == [re.search(r' id="([^"]+)"', botao)[1], ref]
    assert _elemento_por_id(html, ids[0]) == "Enviar avaliação"
    assert _elemento_por_id(html, ids[1]) == titulo
    # Avaliado: o botão desabilitado.
    pk2, titulo2 = cenario.outro_publicado.pk, cenario.outro_publicado.titulo
    avaliado = _tag_com(html, f'id="e-{pk2}"')
    ids = re.search(r'aria-labelledby="([^"]+)"', avaliado)[1].split()
    assert ids == [f"e-{pk2}", f"p-{pk2}-titulo"]
    assert _elemento_por_id(html, ids[0]) == "Avaliado"
    assert _elemento_por_id(html, ids[1]) == titulo2


def test_ids_da_cedula_sao_unicos_com_varios_projetos(client, cenario):
    html = cenario.votante(client).get(ROTA).content.decode()
    ids = re.findall(r'\sid="([^"]+)"', html)
    assert len(ids) > 40 and len(ids) == len(set(ids))
