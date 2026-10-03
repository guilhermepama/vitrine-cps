"""Filtro de log P2 — fatia F7 (specs/03-credenciamento-votacao.md, B1).

Ainda não há views (F4–F6): os registros vêm de LogRecord sintéticos e das
mesmas funções do Django que as views vão acionar (log_response,
response_for_exception, CsrfViewMiddleware). O fluxo /entrar → /visitantes
→ /votar → /votos com assertLogs fica para a F8.
"""

import logging
import unittest

import pytest
from django.core.exceptions import BadRequest
from django.core.handlers.exception import response_for_exception
from django.http import HttpResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.test import RequestFactory
from django.utils.log import log_response

from votacao.logs import FiltroRotasVisitante

ROTAS = ["/entrar", "/visitantes", "/votar", "/votos", "/entrar/", "/votos/"]
MARCADOR = "MARCADOR-SECRETO 203.0.113.7 joao@exemplo.com"
# Valores fictícios do request que não podem aparecer em linha nenhuma.
VAZAMENTOS = [
    "MARCADOR-SECRETO",
    "203.0.113.7",
    "joao@exemplo.com",
    "Joao Fulano",
    "1:1790000000",
    "ab" * 32,
    "3f2b8c1e-0000-4000-8000-00000000c0de",
]

# Idêntico ao trecho de LOGGING proposto na descrição do PR: filtro no
# LOGGER — assertLogs troca os handlers do logger, então um filtro só no
# handler sumiria nos testes.
LOGGERS_FILTRADOS = ["django.request", "django.security", "django.security.csrf", "votacao"]

_tc = unittest.TestCase()


def _request(rota, metodo="get", **extra):
    fabrica = RequestFactory(REMOTE_ADDR="203.0.113.7", **extra)
    fabrica.cookies["token"] = "3f2b8c1e-0000-4000-8000-00000000c0de"
    if metodo == "post":
        return fabrica.post(rota, {"nome": "Joao Fulano", "email": "joao@exemplo.com"})
    return fabrica.get(rota, {"w": "1:1790000000", "sig": "ab" * 32})


def _registro(rota, status, nome="django.request", exc_info=None, metodo="get", **extra):
    return logging.makeLogRecord({
        "name": nome,
        "levelno": logging.ERROR if status >= 500 else logging.WARNING,
        "msg": "%s: %s",
        "args": (MARCADOR, rota),
        "exc_info": exc_info,
        "request": _request(rota, metodo, **extra),
        "status_code": status,
    })


def _exc_info():
    try:
        raise ValueError(MARCADOR)
    except ValueError as exc:
        return (type(exc), exc, exc.__traceback__)


def _sem_vazamento(texto):
    for valor in VAZAMENTOS:
        assert valor not in texto


# --- Filtro isolado ------------------------------------------------------------

@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("status", [400, 403, 404, 405, 409])
def test_4xx_nas_rotas_do_visitante_e_descartado(rota, status):
    assert FiltroRotasVisitante().filter(_registro(rota, status)) is False


@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("nome", ["django.security", "django.security.csrf", "django.security.DisallowedHost"])
def test_django_security_nas_rotas_do_visitante_e_descartado(rota, nome):
    assert FiltroRotasVisitante().filter(_registro(rota, 403, nome=nome, metodo="post")) is False


@pytest.mark.parametrize("rota", ["/entrar", "/visitantes/"])
def test_5xx_reescrito_com_tipo_rota_e_pilha_sem_mensagem(rota):
    record = _registro(rota, 500, exc_info=_exc_info(), metodo="post")

    assert FiltroRotasVisitante().filter(record) is True

    rota_sem_barra = rota.rstrip("/")
    linhas = record.getMessage().splitlines()
    assert linhas[0] == f"ValueError em {rota_sem_barra}"
    assert any("test_logs.py:" in linha and " em _exc_info" in linha for linha in linhas[1:])
    assert record.args == ()
    assert record.exc_info is None
    assert record.exc_text is None
    assert record.stack_info is None
    assert not hasattr(record, "request")
    assert record.status_code == 500
    _sem_vazamento(logging.Formatter().format(record))


def test_5xx_sem_excecao_vira_status_e_rota():
    record = _registro("/votos", 503)
    assert FiltroRotasVisitante().filter(record) is True
    assert record.getMessage() == "HTTP 503 em /votos"
    assert not hasattr(record, "request")


@pytest.mark.parametrize("rota", ["/", "/estacao/1", "/como-votar", "/votacao", "/entrarx", "/admin/login/"])
def test_outras_rotas_passam_intactas(rota):
    record = _registro(rota, 500, exc_info=_exc_info())
    antes = dict(record.__dict__)

    assert FiltroRotasVisitante().filter(record) is True
    assert record.__dict__ == antes


# App servido num subcaminho: request.path é /vitrine/entrar, mas o filtro
# olha path_info (/entrar), o mesmo que o roteador usa.
PREFIXO = {"SCRIPT_NAME": "/vitrine"}


@pytest.mark.parametrize("rota", ["/entrar", "/votos/"])
def test_com_prefixo_de_script_4xx_e_descartado(rota):
    record = _registro(rota, 400, **PREFIXO)
    assert record.request.path == f"/vitrine{rota}"
    assert FiltroRotasVisitante().filter(record) is False


def test_com_prefixo_de_script_5xx_reescrito_com_rota_sem_prefixo():
    record = _registro("/visitantes", 500, exc_info=_exc_info(), metodo="post", **PREFIXO)

    assert FiltroRotasVisitante().filter(record) is True
    assert record.getMessage().startswith("ValueError em /visitantes\n  ")
    assert not hasattr(record, "request")
    _sem_vazamento(logging.Formatter().format(record))


@pytest.mark.parametrize("rota", ["/", "/como-votar", "/vitrine/entrar"])
def test_com_prefixo_de_script_outras_rotas_passam_intactas(rota):
    record = _registro(rota, 500, exc_info=_exc_info(), **PREFIXO)
    antes = dict(record.__dict__)

    assert FiltroRotasVisitante().filter(record) is True
    assert record.__dict__ == antes


@pytest.mark.parametrize("nome", ["votacao", "django.request", "django.security.csrf"])
def test_registro_sem_request_passa_intacto(nome):
    record = logging.makeLogRecord({"name": nome, "msg": "estação %s inativa", "args": (3,)})
    antes = dict(record.__dict__)

    assert FiltroRotasVisitante().filter(record) is True
    assert record.__dict__ == antes


# --- Filtro pendurado no logger, como em LOGGING ------------------------------

@pytest.fixture
def filtro_nos_loggers():
    filtro = FiltroRotasVisitante()
    for nome in LOGGERS_FILTRADOS:
        logging.getLogger(nome).addFilter(filtro)
    yield
    for nome in LOGGERS_FILTRADOS:
        logging.getLogger(nome).removeFilter(filtro)


@pytest.fixture
def sem_filtros_reais():
    # Tira dos loggers os filtros que o LOGGING do settings pendurou, para o
    # controle não depender do settings; restaura no fim.
    salvos = {}
    for nome in LOGGERS_FILTRADOS:
        logger = logging.getLogger(nome)
        salvos[nome] = list(logger.filters)
        logger.filters.clear()
    try:
        yield
    finally:
        for nome, filtros in salvos.items():
            logging.getLogger(nome).filters[:] = filtros


def test_sem_filtro_o_4xx_sai_no_log(sem_filtros_reais):
    # Controle: sem isto, os testes de "nenhum registro" poderiam passar à toa.
    with _tc.assertLogs("django", level="DEBUG"):
        log_response("Bad Request: %s", "/entrar", response=HttpResponse(status=400), request=_request("/entrar"))


@pytest.mark.parametrize("rota", ["/entrar", "/visitantes", "/votar", "/votos"])
def test_no_logger_4xx_nao_sai(filtro_nos_loggers, rota):
    request = _request(rota)
    with _tc.assertNoLogs("django", level="DEBUG"):
        log_response("Bad Request: %s", rota, response=HttpResponse(status=400), request=request)
        response_for_exception(request, BadRequest(MARCADOR))


@pytest.mark.parametrize("rota", ["/visitantes", "/votos"])
def test_no_logger_csrf_nao_sai(filtro_nos_loggers, rota):
    request = _request(rota, metodo="post")
    with _tc.assertNoLogs("django", level="DEBUG"):
        resposta = CsrfViewMiddleware(lambda r: HttpResponse()).process_view(request, lambda r: None, (), {})
    assert resposta.status_code == 403


@pytest.mark.parametrize("rota,metodo", [("/visitantes", "post"), ("/entrar", "get")])
def test_no_logger_5xx_sai_reescrito(filtro_nos_loggers, rota, metodo):
    request = _request(rota, metodo)
    with _tc.assertLogs("django", level="DEBUG") as capturado:
        try:
            raise ValueError(MARCADOR)
        except ValueError as exc:
            resposta = response_for_exception(request, exc)

    assert resposta.status_code == 500
    [record] = capturado.records
    assert record.name == "django.request"
    assert record.getMessage().startswith(f"ValueError em {rota}\n  ")
    assert "test_logs.py:" in record.getMessage()
    assert not hasattr(record, "request")
    assert record.exc_info is None
    _sem_vazamento("\n".join(capturado.output))


def test_no_logger_com_force_script_name_4xx_nao_sai(filtro_nos_loggers, settings):
    settings.FORCE_SCRIPT_NAME = "/vitrine"
    request = _request("/entrar")
    assert request.path == "/vitrine/entrar"
    with _tc.assertNoLogs("django", level="DEBUG"):
        log_response("Bad Request: %s", request.path, response=HttpResponse(status=400), request=request)


def test_no_logger_votacao_sem_request_passa(filtro_nos_loggers):
    with _tc.assertLogs("votacao", level="DEBUG") as capturado:
        logging.getLogger("votacao").warning("estação %s inativa", 3)
    assert capturado.output == ["WARNING:votacao:estação 3 inativa"]
