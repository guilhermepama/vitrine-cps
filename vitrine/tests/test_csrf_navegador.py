"""CSRF como o navegador faz: cabeçalho `Origin` no POST (specs/02-vitrine-publica.md).

O test client padrão não manda `Origin` e não aplica CSRF; por isso o 403 de
produção (10/10) não apareceu no CI. Aqui o CSRF é aplicado e o `Origin` é o
que o navegador mandaria.
"""

import pytest
from django.test import Client

from vitrine.tests import auxiliares as aux

URL = "/grupo/"


def _post_com_origin(origin):
    client = Client(enforce_csrf_checks=True)
    client.get(URL)
    csrf = client.cookies["csrftoken"].value
    return client.post(URL, {"ra": "0000000", "csrfmiddlewaretoken": csrf}, HTTP_ORIGIN=origin)


@pytest.mark.django_db
def test_post_com_a_origem_do_proprio_site_passa_pelo_csrf():
    r = _post_com_origin("http://testserver")
    assert r.status_code == 400  # RA não encontrado, não 403
    assert "Não foi possível acessar com esse RA" in r.content.decode()


@pytest.mark.django_db
def test_post_com_origin_null_e_recusado_pelo_csrf():
    """É o que o navegador manda quando a página tem `Referrer-Policy: no-referrer`."""
    assert _post_com_origin("null").status_code == 403


@pytest.mark.django_db
def test_paginas_do_grupo_com_formulario_post_nao_usam_no_referrer(client):
    # Com `no-referrer`, o navegador serializa o `Origin` do POST do formulário
    # como `null` (padrão Fetch) e o CSRF do Django recusa (teste acima).
    _, token = aux.projeto_com_link()
    for caminho in (URL, f"/grupo/editar/{token}/"):
        resposta = client.get(caminho)
        assert resposta.status_code == 200
        assert 'method="post"' in resposta.content.decode().lower(), caminho
        assert resposta["Referrer-Policy"] != "no-referrer", caminho
