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

import uuid

import pytest
from django.core.signing import Signer

from votacao.cookie_token import COOKIE_TOKEN
from votacao.liberacao import COOKIE_CADASTRO
from votacao.models import Visitante
from votacao.servicos import abrir_votacao, encerrar_votacao
from votacao.tests import fabricas
from votacao.tests.cenario import montar
from votacao.views_voto import ROTA_COMO_VOTAR

pytestmark = pytest.mark.django_db

ROTA = "/votar"
DESABILITADO = '<button type="button" disabled>Votado</button>'


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


def test_projeto_votado_aparece_marcado_e_desabilitado(client, cenario):
    fabricas.voto(cenario.token, cenario.publicado)
    html = cenario.votante(client).get(ROTA).content.decode()
    assert f'data-projeto="{cenario.publicado.pk}"' not in html
    assert DESABILITADO in html
    assert f'data-projeto="{cenario.outro_publicado.pk}"' in html


def test_votos_do_ensaio_nao_aparecem_no_evento_e_vice_versa(client, cenario):
    # Mesmo projeto do evento votado por um token do ensaio (cenário forçado no banco).
    fabricas.voto(cenario.token_ensaio, cenario.publicado)
    html = cenario.votante(client).get(ROTA).content.decode()
    assert f'data-projeto="{cenario.publicado.pk}"' in html
    assert DESABILITADO not in html

    fabricas.voto(cenario.token, cenario.do_ensaio)
    encerrar_votacao(cenario.evento.pk)
    assert abrir_votacao(cenario.ensaio.pk) is None
    html = cenario.votante(client, cenario.token_ensaio, cadastro_de=cenario.ensaio).get(ROTA).content.decode()
    assert f'data-projeto="{cenario.do_ensaio.pk}"' in html
    assert DESABILITADO not in html and "Horta Viva" not in html


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
    _redirect(client.get(ROTA), ROTA_COMO_VOTAR)


def test_token_de_outra_edicao_vai_para_como_votar(client, cenario):
    _redirect(cenario.votante(client, cenario.token_ensaio).get(ROTA), ROTA_COMO_VOTAR)


def test_caminho_da_instrucao_e_o_da_spec():
    assert ROTA_COMO_VOTAR == "/como-votar/"


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
    _redirect(client.get(ROTA), ROTA_COMO_VOTAR)


def test_so_get(client, cenario):
    assert cenario.votante(client).post(ROTA).status_code == 405
