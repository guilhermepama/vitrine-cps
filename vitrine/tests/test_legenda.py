"""Legenda depois do envio (specs/02-vitrine-publica.md, "Imagens, uma por requisição")."""

import pytest
from django.test import Client

from cadastro.models import ImagemProjeto, Projeto
from cadastro.tests import fabricas
from vitrine.tests import auxiliares as aux


def _imagem(projeto, legenda=""):
    return ImagemProjeto.objects.create(projeto=projeto, arquivo=fabricas.imagem(), legenda=legenda, ordem=0)


def _url(token, imagem):
    return f"/grupo/editar/{token}/imagem/{imagem.pk}/legenda/"


@pytest.mark.django_db
def test_grava_a_legenda_sem_trocar_o_arquivo(client):
    p, token = aux.projeto_com_link()
    imagem = _imagem(p)
    arquivo = imagem.arquivo.name
    r = client.post(_url(token, imagem), {"legenda": "  Tela inicial  "})
    assert r.status_code == 302
    imagem.refresh_from_db()
    assert imagem.legenda == "Tela inicial" and imagem.arquivo.name == arquivo
    assert "Legenda salva." in client.get(f"/grupo/editar/{token}/").content.decode()


@pytest.mark.django_db
def test_legenda_vazia_apaga_a_anterior(client):
    p, token = aux.projeto_com_link()
    imagem = _imagem(p, "Antiga")
    assert client.post(_url(token, imagem), {"legenda": ""}).status_code == 302
    imagem.refresh_from_db()
    assert imagem.legenda == ""


@pytest.mark.django_db
def test_legenda_acima_de_120_caracteres_e_recusada(client):
    p, token = aux.projeto_com_link()
    imagem = _imagem(p, "Antiga")
    r = client.post(_url(token, imagem), {"legenda": "x" * 121})
    assert r.status_code == 400
    assert "até 120 caracteres" in r.content.decode()
    imagem.refresh_from_db()
    assert imagem.legenda == "Antiga"


@pytest.mark.django_db
def test_imagem_de_outro_projeto_da_404_e_nada_muda(client):
    p, token = aux.projeto_com_link()
    outro, _ = aux.projeto_com_link(edicao=p.turma.edicao, ra_hmac=aux.hash_ra("7654321"))
    alheia = _imagem(outro, "Original")
    assert client.post(_url(token, alheia), {"legenda": "Invasor"}).status_code == 404
    alheia.refresh_from_db()
    assert alheia.legenda == "Original"


@pytest.mark.django_db
def test_token_invalido_da_404(client):
    p, _ = aux.projeto_com_link()
    imagem = _imagem(p, "Original")
    assert client.post(f"/grupo/editar/nao-existe/imagem/{imagem.pk}/legenda/", {"legenda": "x"}).status_code == 404
    imagem.refresh_from_db()
    assert imagem.legenda == "Original"


@pytest.mark.django_db
def test_get_nao_e_aceito(client):
    p, token = aux.projeto_com_link()
    assert client.get(_url(token, _imagem(p))).status_code == 405


@pytest.mark.django_db
@pytest.mark.parametrize("cenario", ["em_revisao", "publicado", "prazo", "votacao_aberta"])
def test_projeto_nao_editavel_da_403_e_nada_muda(client, cenario):
    if cenario in ("em_revisao", "publicado"):
        status = Projeto.Status.EM_REVISAO if cenario == "em_revisao" else Projeto.Status.PUBLICADO
        p, token = aux.projeto_com_link(status=status)
    else:
        p, token = aux.projeto_com_link()
        (aux.prazo_vencido if cenario == "prazo" else aux.votacao_aberta)(p)
    imagem = _imagem(p, "Original")
    assert client.post(_url(token, imagem), {"legenda": "Nova"}).status_code == 403
    assert client.post(_url(token, imagem), {"legenda": "x" * 121}).status_code == 403
    imagem.refresh_from_db()
    assert imagem.legenda == "Original"


@pytest.mark.django_db
def test_paginas_do_grupo_tem_os_cabecalhos_de_protecao(client):
    p, token = aux.projeto_com_link()
    r = client.post(_url(token, _imagem(p)), {"legenda": "x"})
    assert r["Referrer-Policy"] == "same-origin" and r["X-Robots-Tag"] == "noindex"


@pytest.mark.django_db
def test_legenda_sem_token_csrf_da_403():
    """O fetch do imagens.js manda o `csrfmiddlewaretoken` do próprio formulário; sem ele, 403."""
    p, token = aux.projeto_com_link()
    imagem = _imagem(p, "Tela")
    client = Client(enforce_csrf_checks=True)
    client.get(f"/grupo/editar/{token}/")
    url = _url(token, imagem)
    assert client.post(url, {"legenda": "Sem token"}).status_code == 403
    imagem.refresh_from_db()
    assert imagem.legenda == "Tela"
    csrf = client.cookies["csrftoken"].value
    assert client.post(url, {"legenda": "Com token", "csrfmiddlewaretoken": csrf}, HTTP_ORIGIN="http://testserver").status_code == 302
