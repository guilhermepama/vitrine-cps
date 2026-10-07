"""O token do link de edição não vai para o log da aplicação (spec 02, guardrail 3).

Usa a configuração real de LOGGING (filtro `config.logs.FiltroTokenEdicao`):
o Django registra todo 4xx em `django.request` com o caminho, que leva o token.
"""

import logging
from contextlib import contextmanager

import pytest

from cadastro.models import Projeto
from vitrine.tests import auxiliares as aux


@contextmanager
def _captura():
    """Handler extra em `django.request`: recebe o que passou pelos filtros do logger.

    (O `caplog` fica na raiz, e o logger `django` não propaga até ela.)
    """
    linhas = []

    class _Lista(logging.Handler):
        def emit(self, record):
            linhas.append(self.format(record))

    logger = logging.getLogger("django.request")
    handler = _Lista()
    logger.addHandler(handler)
    try:
        yield linhas
    finally:
        logger.removeHandler(handler)


def _confere(linhas, token):
    assert linhas, "o 4xx deveria continuar gerando linha (só sem o token)"
    texto = "\n".join(linhas)
    assert token not in texto
    assert "/grupo/editar/<token>/" in texto


@pytest.mark.django_db
def test_400_com_token_valido_sai_sem_o_token(client):
    _, token = aux.projeto_com_link()
    with _captura() as linhas:
        r = client.post(f"/grupo/editar/{token}/", aux.dados_de_edicao(acao="invalida"))
    assert r.status_code == 400
    _confere(linhas, token)


@pytest.mark.django_db
def test_403_com_token_valido_sai_sem_o_token(client):
    _, token = aux.projeto_com_link(status=Projeto.Status.EM_REVISAO)
    with _captura() as linhas:
        r = client.post(f"/grupo/editar/{token}/", aux.dados_de_edicao())
    assert r.status_code == 403
    _confere(linhas, token)


@pytest.mark.django_db
def test_404_com_token_valido_sai_sem_o_token(client):
    _, token = aux.projeto_com_link()
    with _captura() as linhas:
        r = client.post(f"/grupo/editar/{token}/imagem/999999/remover/")
    assert r.status_code == 404
    _confere(linhas, token)
