"""Validação de entrada da edição e das imagens (G12) — specs/02-vitrine-publica.md."""

import pytest

from cadastro.tests import fabricas
from vitrine.tests import auxiliares as aux


def url(token):
    return f"/grupo/editar/{token}/"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "campo,valor",
    [
        ("resumo", "r" * 281),
        ("descricao", "d" * 3001),
        ("componente_origem", "c" * 121),
        ("link_demo", "https://exemplo.com/" + "a" * 200),
    ],
)
def test_campo_acima_do_limite_da_400_e_nao_grava(client, campo, valor):
    p, token = aux.projeto_com_link()
    r = client.post(url(token), aux.dados_de_edicao(**{campo: valor}))
    assert r.status_code == 400
    p.refresh_from_db()
    assert p.resumo == "" and p.descricao == "" and p.integrantes.count() == 0


@pytest.mark.django_db
def test_nome_e_papel_do_integrante_acima_de_60_sao_recusados(client):
    p, token = aux.projeto_com_link()
    assert client.post(url(token), aux.dados_de_edicao(integrantes=(("N" * 61, ""),))).status_code == 400
    assert client.post(url(token), aux.dados_de_edicao(integrantes=(("Ana", "P" * 61),))).status_code == 400
    assert p.integrantes.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("token", ["x" * 201, "x" * 500, "!!!" * 10, "a b", "ç" * 5])
def test_token_fora_do_formato_da_404_sem_consultar_o_banco(client, django_assert_num_queries, token):
    with django_assert_num_queries(0):
        assert client.get(url(token)).status_code == 404


@pytest.mark.django_db
def test_legenda_acima_de_120_e_recusada(client):
    p, token = aux.projeto_com_link()
    r = client.post(
        f"/grupo/editar/{token}/imagem/", {"tipo": "extra", "arquivo": fabricas.imagem(), "legenda": "l" * 121}
    )
    assert r.status_code == 400
    assert p.imagens.count() == 0


@pytest.mark.django_db
def test_id_de_imagem_que_nao_e_inteiro_da_404(client):
    _, token = aux.projeto_com_link()
    assert client.post(f"/grupo/editar/{token}/imagem/abc/remover/").status_code == 404
