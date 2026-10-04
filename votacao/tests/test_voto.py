"""Registro do voto POST /votos — fatia F6 (specs/03-credenciamento-votacao.md).

Critérios de aceite fechados aqui (citados em cada bloco):
- "Voto válido → 201 `{"status": "registrado"}`"; segundo voto → 409 genérico.
- Igualdade da rejeição: todos os casos e combinações → 409, corpo byte a
  byte igual, nenhum voto gravado.
- "`projeto_id` malformado [...] → 400 `invalido`, nenhuma query ao banco".
- "Com votação encerrada, [...] `/votos` recusa(m)".
- Liberação: token sem cadastro → 409; nenhum registro de sessão nem cache
  no fluxo `POST /visitantes` → `GET /votar` → `POST /votos`.
- Isolamento: token do ensaio não vota em projeto do evento.
- G4: a trava da edição vem antes das conferências; a constraint barra o
  duplicado mesmo sem a checagem do código.
"""

import ast
import json
import uuid
from pathlib import Path
from unittest import mock

import pytest
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.db import connection
from django.test import Client

from votacao import views_voto
from votacao.cookie_token import COOKIE_TOKEN
from votacao.liberacao import COOKIE_CADASTRO
from votacao.models import Voto
from votacao.servicos import encerrar_votacao
from votacao.tests import fabricas
from votacao.tests.cenario import montar

pytestmark = pytest.mark.django_db

ROTA = "/votos"
REJEITADO = '{"status": "rejeitado", "mensagem": "voto já registrado"}'.encode()
INVALIDO = '{"status": "invalido", "mensagem": "requisição inválida"}'.encode()


@pytest.fixture
def cenario():
    return montar()


def _votar(client, projeto_id):
    return client.post(ROTA, {"projeto_id": str(projeto_id)})


def _rejeitado(resposta, votos=0):
    assert resposta.status_code == 409
    assert resposta.content == REJEITADO
    assert resposta["Content-Type"] == "application/json; charset=utf-8"
    assert not resposta.cookies  # nenhuma diferença de cookie entre os casos
    assert Voto.objects.count() == votos


def test_corpos_sao_os_da_spec():
    assert json.loads(views_voto.REJEITADO) == {"status": "rejeitado", "mensagem": "voto já registrado"}
    assert json.loads(views_voto.INVALIDO) == {"status": "invalido", "mensagem": "requisição inválida"}
    assert json.loads(views_voto.REGISTRADO) == {"status": "registrado"}


def test_voto_valido_registra_e_responde_201(client, cenario):
    resposta = _votar(cenario.votante(client), cenario.publicado.pk)
    assert resposta.status_code == 201
    assert json.loads(resposta.content) == {"status": "registrado"}
    voto = Voto.objects.get()
    assert (voto.token, voto.projeto) == (cenario.token, cenario.publicado)
    assert "no-store" in resposta["Cache-Control"]


def test_projeto_id_com_espacos_ascii_nas_pontas_e_aceito(client, cenario):
    assert _votar(cenario.votante(client), f"  {cenario.publicado.pk} ").status_code == 201


def test_segundo_voto_no_mesmo_projeto_e_409(client, cenario):
    cenario.votante(client)
    assert _votar(client, cenario.publicado.pk).status_code == 201
    _rejeitado(_votar(client, cenario.publicado.pk), votos=1)
    # Outro projeto continua votável.
    assert _votar(client, cenario.outro_publicado.pk).status_code == 201


# --- Igualdade da rejeição -----------------------------------------------------------


def _sem_token(client, c):
    del client.cookies[COOKIE_TOKEN]


def _token(valor):
    def ajustar(client, c):
        client.cookies[COOKIE_TOKEN] = valor

    return ajustar


def _token_do_ensaio(client, c):
    client.cookies[COOKIE_TOKEN] = str(c.token_ensaio.pk)


def _sem_cadastro(client, c):
    del client.cookies[COOKIE_CADASTRO]


def _cadastro_do_ensaio(client, c):
    c.votante(client, cadastro_de=c.ensaio)


def _encerrada(client, c):
    encerrar_votacao(c.evento.pk)


CASOS = {
    "token ausente": [_sem_token],
    "token malformado": [_token("abc")],
    "token sem hífens": [_token(uuid.uuid4().hex)],
    "token inexistente": [_token(str(uuid.uuid4()))],
    "token de outra edição": [_token_do_ensaio],
    "sem cadastro": [_sem_cadastro],
    "cadastro do ensaio": [_cadastro_do_ensaio],
    "votação fechada": [_encerrada],
    "votação fechada + token inexistente": [_encerrada, _token(str(uuid.uuid4()))],
    "token do ensaio + sem cadastro": [_token_do_ensaio, _sem_cadastro],
}


@pytest.mark.parametrize("caso", list(CASOS))
def test_rejeicoes_pelo_token_cadastro_ou_votacao(client, cenario, caso):
    cenario.votante(client)
    for ajuste in CASOS[caso]:
        ajuste(client, cenario)
    _rejeitado(_votar(client, cenario.publicado.pk))


@pytest.mark.parametrize("projeto", ["inexistente", "em_revisao", "do_ensaio"])
def test_rejeicoes_pelo_projeto(client, cenario, projeto):
    projeto_id = 2147483647 if projeto == "inexistente" else getattr(cenario, projeto).pk
    _rejeitado(_votar(cenario.votante(client), projeto_id))


def test_token_do_ensaio_nao_vota_em_projeto_do_evento_nem_com_cadastro_do_evento(client, cenario):
    _rejeitado(_votar(cenario.votante(client, cenario.token_ensaio), cenario.publicado.pk))


def test_votacao_fechada_com_projeto_do_ensaio(client, cenario):
    encerrar_votacao(cenario.evento.pk)
    _rejeitado(_votar(cenario.votante(client), cenario.do_ensaio.pk))


def test_duplicado_barrado_pela_constraint_vira_rejeicao_generica(client, cenario):
    """G4: mesmo que uma checagem do código falhasse, o IntegrityError vira 409."""
    fabricas.voto(cenario.token, cenario.publicado)
    _rejeitado(_votar(cenario.votante(client), cenario.publicado.pk), votos=1)
    # A transação de fora continua usável depois do IntegrityError (savepoint).
    assert _votar(client, cenario.outro_publicado.pk).status_code == 201


# --- Validação de entrada (G12) --------------------------------------------------------

MALFORMADOS = ["abc", "1.5", "", "0", "-1", "+1", "2147483648", "1" * 11, "１", "1\t", "0x1"]


@pytest.mark.parametrize("valor", MALFORMADOS)
def test_projeto_id_malformado_e_400_sem_consultar_o_banco(client, cenario, django_assert_num_queries, valor):
    cenario.votante(client)
    with django_assert_num_queries(0):
        resposta = client.post(ROTA, {"projeto_id": valor})
    assert (resposta.status_code, resposta.content) == (400, INVALIDO)
    assert Voto.objects.count() == 0


@pytest.mark.parametrize("dados", [{}, {"projeto_id": ["1", "1"]}, {"outro": "1"}])
def test_projeto_id_ausente_ou_repetido_e_400(client, cenario, django_assert_num_queries, dados):
    cenario.votante(client)
    with django_assert_num_queries(0):
        resposta = client.post(ROTA, dados)
    assert (resposta.status_code, resposta.content) == (400, INVALIDO)


def test_400_vem_antes_da_trava_mesmo_com_votacao_fechada(client, cenario):
    encerrar_votacao(cenario.evento.pk)
    assert client.post(ROTA, {"projeto_id": "abc"}).content == INVALIDO


def test_sem_csrf_e_403(cenario):
    client = cenario.votante(Client(enforce_csrf_checks=True))
    assert _votar(client, cenario.publicado.pk).status_code == 403
    assert Voto.objects.count() == 0


def test_so_post(client, cenario):
    assert cenario.votante(client).get(ROTA).status_code == 405


def test_trava_a_edicao_antes_de_conferir(client, cenario):
    with mock.patch.object(views_voto, "edicao_em_votacao", wraps=views_voto.edicao_em_votacao) as espia:
        _votar(cenario.votante(client), cenario.publicado.pk)
    espia.assert_called_once_with(travar=True)


# --- Fluxo sem sessão nem cache --------------------------------------------------------


def _linhas_de_cache():
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM cache_django")
        return cursor.fetchone()[0]


def test_fluxo_cadastro_cedula_voto_nao_grava_sessao_nem_cache(client, cenario):
    call_command("createcachetable", verbosity=0)
    cenario.votante(client)
    del client.cookies[COOKIE_CADASTRO]
    antes = (Session.objects.count(), _linhas_de_cache())
    envio = {"nome": "Ana Souza", "email": "ana@example.com", "telefone": "", "consentimento": "on"}
    assert client.post("/visitantes", envio).status_code == 302
    assert client.get("/votar").status_code == 200
    assert _votar(client, cenario.publicado.pk).status_code == 201
    assert (Session.objects.count(), _linhas_de_cache()) == antes


def test_voto_sem_logger():
    arvore = ast.parse((Path(__file__).resolve().parents[1] / "views_voto.py").read_text())
    nomes = {n.id for n in ast.walk(arvore) if isinstance(n, ast.Name)}
    nomes |= {a.name for n in ast.walk(arvore) if isinstance(n, ast.Import | ast.ImportFrom) for a in n.names}
    assert not nomes & {"logging", "logger", "getLogger"}
