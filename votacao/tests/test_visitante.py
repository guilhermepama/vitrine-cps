"""Cadastro do visitante e cookie de cadastro — fatia F5
(specs/03-credenciamento-votacao.md).

Critérios de aceite fechados aqui (citados em cada bloco):
- Formulário de visitante: GET com e sem cadastro válido, sem edição em
  votação, sem sessão nem cache.
- Visitante: matriz de nome, email, telefone e consentimento; edicao_id da
  edição em votação mesmo com cookie de token de outra edição; código sem
  token nem estação; consentimento_em na hora cheia.
- "Com votação encerrada, [...] POST /visitantes [...] recusa(m)".
- Liberação: cookie de cadastro igual para dois visitantes da mesma edição.
- Isolamento: visitante do ensaio fica com o ensaio; o do evento, com o evento.
- B1: ids UUID v4; nenhuma linha de log em POST /visitantes (P2).

A parte do /votar ("não libera a cédula", "mostra a cédula") fecha na F6.
"""

import ast
import contextlib
import unittest
import uuid
from datetime import date, datetime, timezone as dt_timezone
from pathlib import Path
from unittest import mock

import pytest
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.signing import Signer
from django.db import connection
from django.test import Client

from cadastro.tests import fabricas as cadastro
from votacao import views_visitante
from votacao.liberacao import COOKIE_CADASTRO, valor_do_cookie
from votacao.models import Visitante
from votacao.servicos import abrir_votacao, edicao_em_votacao, encerrar_votacao
from votacao.tests import fabricas
from votacao.tests.fabricas import BRASILIA

pytestmark = pytest.mark.django_db

ROTA = "/visitantes"
TEXTO_LGPD = (
    "Aceito que o Centro Paula Souza (Fatec e Etec Olímpia) use meu nome, "
    "e-mail e telefone para enviar comunicações sobre eventos e cursos."
)
MENSAGEM = "Não foi possível concluir o cadastro. Confira os campos."
QR_EXPIRADO = "QR expirado — escaneie novamente na estação"
LOGGERS = ["django", "django.request", "django.security", "django.security.csrf", "votacao"]

_tc = unittest.TestCase()


def _abrir(edicao):
    assert abrir_votacao(edicao.pk) is None
    edicao.refresh_from_db()
    return edicao


@pytest.fixture
def evento():
    return _abrir(cadastro.edicao())


def _ensaio():
    return cadastro.edicao(nome="Ensaio 2026/2", data_evento=date(2026, 10, 22))


def _dados(**campos):
    dados = {"nome": "Ana Souza", "email": "ana@example.com", "telefone": "", "consentimento": "on"}
    dados.update(campos)
    return {k: v for k, v in dados.items() if v is not None}


def _postar(client, **campos):
    return client.post(ROTA, _dados(**campos))


def _recusado(resposta):
    """400 com a mensagem genérica, nada gravado, sem cookie de cadastro."""
    assert resposta.status_code == 400
    assert MENSAGEM in resposta.content.decode()
    assert COOKIE_CADASTRO not in resposta.cookies
    assert Visitante.objects.count() == 0


def _aceito(resposta):
    assert resposta.status_code == 302
    assert resposta["Location"] == "/votar"
    assert Visitante.objects.count() == 1
    return Visitante.objects.get()


def _linhas_de_cache():
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM cache_django")
        return cursor.fetchone()[0]


@contextlib.contextmanager
def _sem_logs():
    with contextlib.ExitStack() as pilha:
        for nome in LOGGERS:
            pilha.enter_context(_tc.assertNoLogs(nome, level="DEBUG"))
        yield


# --- GET /visitantes -------------------------------------------------------------


def test_get_mostra_formulario_com_texto_do_consentimento(client, evento):
    token = fabricas.token(fabricas.estacao(evento))
    for cookies in ({}, {"token": str(token.pk)}):
        client.cookies.clear()
        for nome, valor in cookies.items():
            client.cookies[nome] = valor
        resposta = client.get(ROTA)
        assert resposta.status_code == 200
        corpo = resposta.content.decode()
        assert TEXTO_LGPD in corpo
        for campo in ("nome", "email", "telefone", "consentimento"):
            assert f'name="{campo}"' in corpo
        assert "no-store" in resposta["Cache-Control"]


def test_get_com_cadastro_valido_vai_para_a_cedula(client, evento):
    client.cookies[COOKIE_CADASTRO] = valor_do_cookie(evento)
    resposta = client.get(ROTA)
    assert resposta.status_code == 302
    assert resposta["Location"] == "/votar"
    assert b"<form" not in resposta.content
    assert Visitante.objects.count() == 0


def test_get_com_cookie_adulterado_ou_do_ensaio_mostra_formulario(client):
    ensaio = _abrir(_ensaio())
    do_ensaio = valor_do_cookie(ensaio)
    assert encerrar_votacao(ensaio.pk) is None
    evento = _abrir(cadastro.edicao())
    adulterados = [
        do_ensaio,
        f"{evento.pk}:assinatura-falsa",
        do_ensaio.replace(f"{ensaio.pk}:", f"{evento.pk}:", 1),
        Signer(salt="outro.sal").sign(str(evento.pk)),
        str(evento.pk),
    ]
    for valor in adulterados:
        client.cookies[COOKIE_CADASTRO] = valor
        resposta = client.get(ROTA)
        assert resposta.status_code == 200, valor
        assert TEXTO_LGPD in resposta.content.decode()


def test_get_sem_edicao_em_votacao_e_qr_expirado(client):
    nunca_aberta = cadastro.edicao()
    resposta = client.get(ROTA)
    assert resposta.status_code == 400
    assert QR_EXPIRADO in resposta.content.decode()
    assert b"<form" not in resposta.content

    _abrir(nunca_aberta)
    encerrar_votacao(nunca_aberta.pk)
    client.cookies[COOKIE_CADASTRO] = valor_do_cookie(nunca_aberta)
    depois = client.get(ROTA)
    assert depois.status_code == 400
    assert depois.content == resposta.content


def test_get_ignora_query_string_e_nao_grava_sessao_nem_cache(client, evento):
    call_command("createcachetable", verbosity=0)
    sessoes, cache = Session.objects.count(), _linhas_de_cache()
    resposta = client.get(ROTA, {"nome": "Ana", "w": "1:1790000000", "edicao": "999"})
    assert resposta.status_code == 200
    assert "Ana" not in resposta.content.decode()
    assert (Session.objects.count(), _linhas_de_cache()) == (sessoes, cache)
    assert Visitante.objects.count() == 0


# --- POST /visitantes: matriz de validação ------------------------------------------


def test_cadastro_valido_grava_e_vai_para_a_cedula(client, evento):
    visitante = _aceito(_postar(client, nome="  Ana Souza  ", email=" ana@example.com ", extra="ignorado"))
    assert (visitante.nome, visitante.email, visitante.telefone) == ("Ana Souza", "ana@example.com", None)
    assert visitante.edicao == evento


@pytest.mark.parametrize("nome", ["A", "A" * 121, None, "", "   ", "Ana\x07Souza", "Ana\x00", "\tAna", "Ana\n", "Ana\x7f", "Ana\x85"])
def test_nome_invalido_400(client, evento, nome):
    _recusado(_postar(client, nome=nome))


@pytest.mark.parametrize("nome", ["Al", "A" * 120, " " + "A" * 120 + " "])
def test_nome_nos_limites_aceito(client, evento, nome):
    assert _aceito(_postar(client, nome=nome)).nome == nome.strip(" ")


def _email(tamanho):
    # 64 + 1 + 63 + 1 + 63 + 1 = 193; o último rótulo completa o tamanho.
    return "a" * 64 + "@" + "b" * 63 + "." + "c" * 63 + "." + "d" * (tamanho - 197) + ".com"


@pytest.mark.parametrize("email", [None, "", "ana", "ana@", "@example.com", "ana@example", "ana souza@example.com", _email(255)])
def test_email_invalido_400(client, evento, email):
    _recusado(_postar(client, email=email))


def test_email_com_254_aceito(client, evento):
    email = _email(254)
    assert len(email) == 254
    assert _aceito(_postar(client, email=email)).email == email


@pytest.mark.parametrize(
    "telefone",
    ["179999999", "55179999999999", "(17) 9999A-9999", "(17) 9 9 9 9 9 - 9999", "17.99999.9999", "551799999999999", "+1 (17) 99999-9999", "١٧٩٩٩٩٩٩٩٩٩"],
)
def test_telefone_invalido_400(client, evento, telefone):
    if telefone == "(17) 9 9 9 9 9 - 9999":
        assert len(telefone) == 21  # só o tamanho reprova: tem 11 dígitos
    _recusado(_postar(client, telefone=telefone))


@pytest.mark.parametrize(
    ("telefone", "gravado"),
    [("", None), (None, None), ("(17) 99999-9999", "17999999999"), ("+55 17 99999-9999", "5517999999999"),
     ("(17) 3333-4444", "1733334444"), ("551733334444", "551733334444")],
)
def test_telefone_aceito_gravado_so_com_digitos(client, evento, telefone, gravado):
    assert _aceito(_postar(client, telefone=telefone)).telefone == gravado


@pytest.mark.parametrize("consentimento", [None, "", "false"])
def test_sem_consentimento_400(client, evento, consentimento):
    _recusado(_postar(client, consentimento=consentimento))


def test_erro_nao_diz_qual_campo_barrou(client, evento):
    corpos = {_postar(client, **campo).content.decode().split("<form")[0]
              for campo in ({"nome": "A"}, {"email": "x"}, {"telefone": "1"}, {"consentimento": None})}
    assert len(corpos) == 1


# --- POST /visitantes: edição, horário e cookie -----------------------------------


def test_edicao_vem_da_votacao_mesmo_com_token_de_outra_edicao(client):
    ensaio = _abrir(_ensaio())
    token_do_ensaio = fabricas.token(fabricas.estacao(ensaio))
    encerrar_votacao(ensaio.pk)
    evento = _abrir(cadastro.edicao())
    client.cookies["token"] = str(token_do_ensaio.pk)
    client.cookies[COOKIE_CADASTRO] = valor_do_cookie(ensaio)
    assert _aceito(_postar(client)).edicao == evento


def test_consentimento_truncado_para_a_hora_em_brasilia(client, evento):
    aceite = datetime(2026, 10, 25, 19, 42, 17, 654321, tzinfo=BRASILIA)
    with mock.patch("django.utils.timezone.now", return_value=aceite.astimezone(dt_timezone.utc)):
        _aceito(_postar(client))
    gravado = Visitante.objects.get().consentimento_em
    assert gravado == datetime(2026, 10, 25, 22, 0, tzinfo=dt_timezone.utc)
    assert gravado.astimezone(BRASILIA).replace(tzinfo=None) == datetime(2026, 10, 25, 19, 0)
    assert (gravado.minute, gravado.second, gravado.microsecond) == (0, 0, 0)


def test_cadastro_trava_a_edicao_em_votacao(client, evento):
    with mock.patch.object(views_visitante, "edicao_em_votacao", wraps=edicao_em_votacao) as lida:
        _aceito(_postar(client))
    lida.assert_called_once_with(travar=True)


def test_sem_edicao_em_votacao_post_e_qr_expirado(client):
    edicao = cadastro.edicao()
    pagina = client.get(ROTA).content
    for momento in ("nunca aberta", "encerrada"):
        resposta = _postar(client)
        assert resposta.status_code == 400, momento
        assert resposta.content == pagina
        assert COOKIE_CADASTRO not in resposta.cookies
        assert Visitante.objects.count() == 0
        if momento == "nunca aberta":
            _abrir(edicao)
            encerrar_votacao(edicao.pk)


def test_cookie_de_cadastro_igual_para_toda_a_edicao(evento):
    valores = []
    for nome in ("Ana Souza", "Bruno Lima"):
        resposta = _postar(Client(), nome=nome)
        cookie = resposta.cookies[COOKIE_CADASTRO]
        assert cookie["httponly"] and cookie["secure"]
        assert cookie["samesite"] == "Lax"
        assert cookie["max-age"] == 86400
        valores.append(cookie.value)
    assert valores[0] == valores[1] == Signer(salt="votacao.cadastro").sign(str(evento.pk))


def test_post_nao_grava_sessao_nem_cache(client, evento):
    call_command("createcachetable", verbosity=0)
    sessoes, cache = Session.objects.count(), _linhas_de_cache()
    _aceito(_postar(client))
    _postar(client, nome="A")
    assert (Session.objects.count(), _linhas_de_cache()) == (sessoes, cache)


def test_isolamento_ensaio_e_evento():
    ensaio = _abrir(_ensaio())
    _postar(Client(), nome="No Ensaio")
    cookie_ensaio = Client()
    _postar(cookie_ensaio)
    encerrar_votacao(ensaio.pk)
    evento = _abrir(cadastro.edicao())
    # O cookie do ensaio não vale no evento: formulário de novo e novo registro.
    assert cookie_ensaio.get(ROTA).status_code == 200
    _postar(cookie_ensaio, nome="No Evento")
    edicoes = dict(Visitante.objects.values_list("nome", "edicao_id"))
    assert edicoes == {"No Ensaio": ensaio.pk, "Ana Souza": ensaio.pk, "No Evento": evento.pk}


def test_ids_de_visitante_sao_uuid_v4(client, evento):
    _postar(client, nome="Primeiro")
    _postar(client, nome="Segundo")
    ids = list(Visitante.objects.values_list("id", flat=True))
    assert len(ids) == 2
    assert all(isinstance(i, uuid.UUID) and i.version == 4 for i in ids)


# --- P2: nenhuma linha de log -------------------------------------------------------


def test_post_valido_invalido_e_fechado_nao_geram_log(client, evento):
    with _sem_logs():
        assert _postar(client).status_code == 302
        assert _postar(client, nome="A", email="x").status_code == 400
        assert client.get(ROTA).status_code == 302
    encerrar_votacao(evento.pk)
    with _sem_logs():
        assert _postar(client).status_code == 400
        assert client.get(ROTA).status_code == 400


def test_csrf_recusado_sem_log(evento):
    with _sem_logs():
        assert Client(enforce_csrf_checks=True).post(ROTA, _dados()).status_code == 403
    assert Visitante.objects.count() == 0


# --- Revisão de código: o cadastro não lê token nem estação --------------------------

MODULOS = ["views_visitante.py", "forms.py", "liberacao.py", "respostas.py"]
PROIBIDOS = ("token", "estacao", "localstorage")


def _identificadores(caminho):
    arvore = ast.parse(caminho.read_text())
    docstrings = {id(n.body[0].value) for n in ast.walk(arvore)
                  if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and ast.get_docstring(n)}
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name):
            yield no.id
        elif isinstance(no, ast.Attribute):
            yield no.attr
        elif isinstance(no, ast.alias):
            yield no.name
        elif isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in docstrings:
            yield no.value


def test_cadastro_nao_le_token_nem_estacao():
    pasta = Path(views_visitante.__file__).parent
    for modulo in MODULOS:
        nomes = list(_identificadores(pasta / modulo))
        assert not [n for n in nomes if any(p in n.lower() for p in PROIBIDOS)], modulo
        if modulo != "liberacao.py":
            assert "COOKIES" not in nomes, modulo
