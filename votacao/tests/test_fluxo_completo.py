"""Fluxo completo nas duas edições — fatia F8 (specs/03-credenciamento-votacao.md).

/estacao → /entrar → /visitantes → /votar → /votos, primeiro no ensaio
(22/10), depois no evento, com o MESMO celular (mesmos cookies), pelas rotas
reais (`reverse`) e com CSRF ligado.

Critérios de aceite fechados aqui:
- Isolamento por edição, todos num teste só: token do ensaio não vota no
  evento; re-scan no evento com cookie do ensaio emite token novo e o do
  ensaio fica intacto; votos de uma edição não aparecem marcados na outra;
  cada visitante fica com a sua edição; encerrar o ensaio e abrir o evento
  não altera tokens, votos nem visitantes do ensaio.
- B1/P2: com o LOGGING real do settings (filtro no logger, PR #27), o
  fluxo inteiro — com sucesso e com rejeições 400, 409 e 403 de CSRF — não
  gera nenhum registro de log; exceção forçada em GET /entrar e POST
  /visitantes vira um registro só, sem a mensagem nem dados do visitante.
"""

import json
import re
import unittest
from datetime import date
from unittest import mock
from urllib.parse import urlsplit

import pytest
from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from cadastro.models import Projeto
from cadastro.tests import fabricas as cadastro
from votacao import views_estacao
from votacao.models import Token, Visitante, Voto
from votacao.servicos import abrir_votacao, encerrar_votacao
from votacao.tests import fabricas

pytestmark = pytest.mark.django_db

PUBLICADO = Projeto.Status.PUBLICADO
LOGGERS = ["django", "votacao"]  # django.request/.security/.csrf propagam para "django"
_tc = unittest.TestCase()


def _edicao(nome, data_evento, curso):
    edicao = cadastro.edicao(nome=nome, data_evento=data_evento)
    projeto = cadastro.projeto(cadastro.turma(edicao, curso), titulo=f"Projeto do {nome}", status=PUBLICADO)
    return edicao, projeto, fabricas.estacao(edicao, nome=f"Entrada {nome}")


@pytest.fixture
def operador():
    usuario = User.objects.create_user("estacao1", password="x", is_staff=True)
    usuario.user_permissions.add(Permission.objects.get(codename="operar_estacao"))
    cliente = Client()
    cliente.force_login(usuario)
    return cliente


def _url_do_qr(operador, estacao):
    """A URL que o QR da página da estação codifica (capturada antes de virar SVG)."""
    with mock.patch.object(views_estacao, "svg_do_qr", wraps=views_estacao.svg_do_qr) as qr:
        assert operador.get(reverse("votacao:estacao", args=[estacao.pk])).status_code == 200
    partes = urlsplit(qr.call_args.args[0])
    assert partes.path == reverse("votacao:entrar")
    return f"{partes.path}?{partes.query}"


def _csrf(html):
    return re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)[1]


def _votar(celular, projeto, csrf=True):
    cabecalho = {"HTTP_X_CSRFTOKEN": celular.cookies["csrftoken"].value} if csrf else {}
    return celular.post(reverse("votacao:votos"), {"projeto_id": str(projeto.pk)}, **cabecalho)


def _percorrer(celular, operador, estacao, projeto, de_fora):
    """Um visitante do QR até o voto, com as rejeições no caminho. Devolve o token."""
    url = _url_do_qr(operador, estacao)
    assert celular.get(url.replace("sig=", "sig=0")).status_code == 400  # sig adulterada
    entrada = celular.get(url)
    assert entrada.status_code == 200
    destino = re.search(r'id="destino"[^>]*>("[^"]+")', entrada.content.decode())[1]
    assert json.loads(destino) == reverse("votacao:visitantes")

    formulario = celular.get(reverse("votacao:visitantes"))
    assert formulario.status_code == 200
    # Sem cadastro, a cédula manda de volta ao formulário.
    assert celular.get(reverse("votacao:votar"))["Location"] == reverse("votacao:visitantes")
    dados = {
        "nome": "Ana Souza",
        "email": "ana@example.com",
        "telefone": "",
        "consentimento": "on",
        "csrfmiddlewaretoken": _csrf(formulario.content.decode()),
    }
    assert celular.post(reverse("votacao:visitantes"), {**dados, "nome": "A"}).status_code == 400
    assert celular.post(reverse("votacao:visitantes"), dados)["Location"] == reverse("votacao:votar")

    cedula = celular.get(reverse("votacao:votar")).content.decode()
    assert f'data-projeto="{projeto.pk}"' in cedula  # não votado, mesmo com votos na outra edição
    assert de_fora.titulo not in cedula
    assert _votar(celular, projeto, csrf=False).status_code == 403
    assert _votar(celular, de_fora).status_code == 409  # projeto da outra edição
    csrf = celular.cookies["csrftoken"].value
    assert celular.post(reverse("votacao:votos"), {"projeto_id": "abc"}, HTTP_X_CSRFTOKEN=csrf).status_code == 400
    assert _votar(celular, projeto).status_code == 201
    assert _votar(celular, projeto).status_code == 409  # duplicado
    assert f'data-projeto="{projeto.pk}"' not in celular.get(reverse("votacao:votar")).content.decode()
    return Token.objects.get(pk=celular.cookies["token"].value)


def _retrato(edicao):
    """Tokens, votos e visitantes de uma edição, para comparar antes e depois."""
    return (
        sorted(Token.objects.filter(estacao__edicao=edicao).values_list("pk", "estacao_id", "criado_em")),
        sorted(Voto.objects.filter(token__estacao__edicao=edicao).values_list("pk", "token_id", "projeto_id", "criado_em")),
        sorted(Visitante.objects.filter(edicao=edicao).values_list("pk", "nome", "email", "consentimento_em")),
    )


def test_ensaio_e_evento_de_ponta_a_ponta_sem_misturar_nada(operador):
    call_command("createcachetable", verbosity=0)
    dsm = cadastro.curso("DSM")
    ensaio, projeto_ensaio, estacao_ensaio = _edicao("Ensaio 2026/2", date(2026, 10, 22), dsm)
    evento, projeto_evento, estacao_evento = _edicao("2026/2", date(2026, 10, 29), dsm)
    celular = Client(enforce_csrf_checks=True)

    with _tc.assertNoLogs(LOGGERS[0], level="DEBUG"), _tc.assertNoLogs(LOGGERS[1], level="DEBUG"):
        assert abrir_votacao(ensaio.pk) is None
        token_ensaio = _percorrer(celular, operador, estacao_ensaio, projeto_ensaio, de_fora=projeto_evento)
        assert encerrar_votacao(ensaio.pk) is None
        antes = _retrato(ensaio)

        # Com o ensaio encerrado, o mesmo celular não vota mais nele.
        assert _votar(celular, projeto_ensaio).status_code == 409
        assert abrir_votacao(evento.pk) is None
        # O token do ensaio não vota no evento, nem com cadastro do evento depois.
        token_evento = _percorrer(celular, operador, estacao_evento, projeto_evento, de_fora=projeto_ensaio)
        antigo = Client(enforce_csrf_checks=True)
        for nome in ("cadastro", "csrftoken"):
            antigo.cookies[nome] = celular.cookies[nome].value
        antigo.cookies["token"] = str(token_ensaio.pk)
        assert _votar(antigo, projeto_evento).status_code == 409

    assert token_evento != token_ensaio
    assert (token_ensaio.estacao, token_evento.estacao) == (estacao_ensaio, estacao_evento)
    assert _retrato(ensaio) == antes
    assert list(Voto.objects.filter(token=token_ensaio).values_list("projeto", flat=True)) == [projeto_ensaio.pk]
    assert list(Voto.objects.filter(token=token_evento).values_list("projeto", flat=True)) == [projeto_evento.pk]
    assert sorted(Visitante.objects.values_list("edicao__nome", flat=True)) == ["2026/2", "Ensaio 2026/2"]


# --- 5xx pelas views reais, com o LOGGING real ------------------------------------

MARCADOR = "MARCADOR-SECRETO"
IP_FICTICIO = "203.0.113.7"


@pytest.mark.parametrize("rota", ["entrar", "visitantes"])
def test_excecao_na_view_vira_um_registro_sem_mensagem_nem_dados(rota):
    """Exceção forçada em GET /entrar e POST /visitantes: um registro de erro
    com tipo, rota e pilha; sem a mensagem, IP, token, cookie, w, sig, nome
    ou email (B1)."""
    call_command("createcachetable", verbosity=0)
    assert abrir_votacao(cadastro.edicao(nome="2026/2").pk) is None
    token = "3f2b8c1e-0000-4000-8000-00000000c0de"
    celular = Client(raise_request_exception=False, REMOTE_ADDR=IP_FICTICIO)
    celular.cookies["token"] = token
    alvo = {"entrar": "votacao.views_entrar.ler_janela", "visitantes": "votacao.views_visitante.VisitanteForm"}[rota]
    with mock.patch(alvo, side_effect=ValueError(MARCADOR)), _tc.assertLogs("django", level="DEBUG") as capturado:
        if rota == "entrar":
            resposta = celular.get(reverse("votacao:entrar"), {"w": "1:1790000000", "sig": "ab" * 32})
        else:
            dados = {"nome": "Joao Fulano", "email": "joao@exemplo.com", "consentimento": "on"}
            resposta = celular.post(reverse("votacao:visitantes"), dados)
    assert resposta.status_code == 500
    [registro] = capturado.records
    texto = "\n".join(capturado.output)
    assert registro.name == "django.request"
    assert registro.getMessage().startswith(f"ValueError em {reverse('votacao:' + rota)}\n")
    assert ".py" in texto  # pilha com arquivo e linha
    assert not hasattr(registro, "request")
    for valor in (MARCADOR, IP_FICTICIO, token, "1:1790000000", "ab" * 32, "Joao Fulano", "joao@exemplo.com"):
        assert valor not in texto
