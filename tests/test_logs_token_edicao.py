"""O token do link de edição não vai para o log (spec 02, guardrail 3).

O Django registra todo 4xx/5xx em `django.request` com o caminho, e a falha
de CSRF em `django.security.csrf`. Em `/grupo/editar/<token>/...` o caminho
leva o token: o filtro troca o segmento por `<token>`.

Os testes de request exercitam o filtro de logger (configurado em LOGGING);
o do handler `console` é a mesma classe.
"""

import logging
import sys
from contextlib import contextmanager

from django.test import RequestFactory

from config.logs import FiltroTokenEdicao

TOKEN = "token-de-teste-do-grupo-000000000"  # falso, sem entropia (gitleaks)


@contextmanager
def _captura(logger):
    """Handler extra no logger: recebe o que passou pelos filtros do logger.
    (O `caplog` fica na raiz, e o logger `django` não propaga até ela.)"""
    linhas = []

    class _Lista(logging.Handler):
        def emit(self, record):
            linhas.append(self.format(record))

    handler = _Lista()
    logger.addHandler(handler)
    try:
        yield linhas
    finally:
        logger.removeHandler(handler)


def test_404_no_link_de_edicao_sai_sem_o_token(client):
    logger = logging.getLogger("django.request")
    with _captura(logger) as linhas:
        resposta = client.get(f"/grupo/editar/{TOKEN}/imagem/")
    assert resposta.status_code == 404
    assert linhas, "o 404 deveria continuar gerando linha (só sem o token)"
    texto = "\n".join(linhas)
    assert TOKEN not in texto
    assert "/grupo/editar/<token>/imagem/" in texto


def test_outras_rotas_nao_mudam(client):
    logger = logging.getLogger("django.request")
    with _captura(logger) as linhas:
        client.get("/projeto/nao-existe/")
    assert any("/projeto/nao-existe/" in linha for linha in linhas)


def _registro(nome, nivel, msg, args, caminho, exc_info=None, status=403):
    registro = logging.LogRecord(nome, nivel, __file__, 1, msg, args, exc_info)
    registro.request = RequestFactory().post(caminho)
    registro.status_code = status
    return registro


def test_csrf_no_link_de_edicao_sai_sem_o_token():
    caminho = f"/grupo/editar/{TOKEN}/"
    registro = _registro(
        "django.security.csrf", logging.WARNING, "Forbidden (%s): %s", ("CSRF token missing.", caminho), caminho
    )
    assert FiltroTokenEdicao().filter(registro) is True
    assert registro.getMessage() == "Forbidden (CSRF token missing.): /grupo/editar/<token>/"
    assert not hasattr(registro, "request")


def test_5xx_no_link_de_edicao_tira_o_token_tambem_do_traceback():
    caminho = f"/grupo/editar/{TOKEN}/"
    try:
        raise ValueError(f"token {TOKEN} quebrou")
    except ValueError:
        exc_info = sys.exc_info()
    registro = _registro(
        "django.request", logging.ERROR, "Internal Server Error: %s", (caminho,), caminho, exc_info, 500
    )
    assert FiltroTokenEdicao().filter(registro) is True
    texto = logging.Formatter().format(registro)
    assert TOKEN not in texto
    assert "ValueError: token <token> quebrou" in texto
    assert "Internal Server Error: /grupo/editar/<token>/" in texto


def test_registro_sem_request_ou_de_outra_rota_passa_intacto():
    sem_request = logging.LogRecord("django", logging.INFO, __file__, 1, "x %s", ("y",), None)
    assert FiltroTokenEdicao().filter(sem_request) is True
    assert sem_request.args == ("y",)

    outra = _registro("django.request", logging.WARNING, "Not Found: %s", ("/projeto/a/",), "/projeto/a/", status=404)
    assert FiltroTokenEdicao().filter(outra) is True
    assert outra.args == ("/projeto/a/",)
    assert hasattr(outra, "request")
