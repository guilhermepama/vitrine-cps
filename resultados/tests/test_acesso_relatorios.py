"""Acesso e validação do relatório operacional e do export de visitantes
(specs/04-resultados.md, fatia 3). A rota do ranking está em test_acesso.py.

Critérios de aceite fechados aqui (rotas operacional e CSV):
- Usuário anônimo → redirect para o login
- Autenticado não admin (sem `is_staff`) com `ver_resultados` e
  `exportar_visitantes` → 403, inclusive no CSV
- Admin sem permissão (grupo `digitacao-banca`) → 403
- Admin com `ver_resultados` mas sem `exportar_visitantes` → 403 no CSV
- `edicao_id` não inteiro (`abc`, `-1`, `1.5`) → 404
- `edicao_id` inteiro sem edição (`0`, inexistente) → 404; POST → 405
"""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from banca.sinais import GRUPO_DIGITACAO
from resultados.tests import cenario

pytestmark = pytest.mark.django_db

OPERACIONAL = ("resultados:operacional", "ver_resultados")
CSV = ("resultados:visitantes_csv", "exportar_visitantes")
ROTAS = pytest.mark.parametrize("rota", [OPERACIONAL, CSV], ids=["operacional", "csv"])


@pytest.fixture
def edicao():
    return cenario.edicao({"DSM": [("Agenda", 3, 8)]})[0]


def url(rota, edicao_id):
    return reverse(rota[0], args=[edicao_id])


@ROTAS
def test_anonimo_vai_para_o_login_do_admin(client, edicao, rota):
    resposta = client.get(url(rota, edicao.pk))
    assert resposta.status_code == 302
    assert resposta.url == f"{reverse('admin:login')}?next={url(rota, edicao.pk)}"


@ROTAS
def test_nao_admin_com_as_duas_permissoes_recebe_403(client, edicao, rota):
    client.force_login(cenario.usuario(staff=False, perms=("ver_resultados", "exportar_visitantes")))
    resposta = client.get(url(rota, edicao.pk))
    assert resposta.status_code == 403
    assert "no-store" in resposta["Cache-Control"]


@ROTAS
def test_admin_do_grupo_digitacao_banca_recebe_403(client, edicao, rota):
    u = cenario.usuario(perms=())
    u.groups.add(Group.objects.get(name=GRUPO_DIGITACAO))
    client.force_login(u)
    assert client.get(url(rota, edicao.pk)).status_code == 403


def test_ver_resultados_sem_exportar_visitantes_recebe_403_no_csv(client, edicao):
    client.force_login(cenario.usuario(perms=("ver_resultados",)))
    assert client.get(url(OPERACIONAL, edicao.pk)).status_code == 200
    resposta = client.get(url(CSV, edicao.pk))
    assert resposta.status_code == 403
    assert "no-store" in resposta["Cache-Control"]


def test_exportar_visitantes_sem_ver_resultados_nao_ve_o_operacional(client, edicao):
    client.force_login(cenario.usuario(perms=("exportar_visitantes",)))
    assert client.get(url(CSV, edicao.pk)).status_code == 200
    assert client.get(url(OPERACIONAL, edicao.pk)).status_code == 403


@ROTAS
def test_admin_com_a_permissao_da_rota_ve_sem_cache(client, edicao, rota):
    client.force_login(cenario.usuario(perms=(rota[1],)))
    resposta = client.get(url(rota, edicao.pk))
    assert resposta.status_code == 200
    assert "no-store" in resposta["Cache-Control"]


@ROTAS
def test_superusuario_ve(client, edicao, rota):
    client.force_login(cenario.usuario(perms=(), is_superuser=True))
    assert client.get(url(rota, edicao.pk)).status_code == 200


@ROTAS
def test_403_vem_antes_do_404(client, rota):
    client.force_login(cenario.usuario(perms=()))
    assert client.get(url(rota, 999_999)).status_code == 403


@pytest.mark.parametrize("segmento", ["abc", "-1", "1.5"])
@pytest.mark.parametrize("sufixo", ["operacional/", "visitantes.csv"])
def test_segmento_nao_inteiro_e_rota_inexistente(client, edicao, segmento, sufixo):
    client.force_login(cenario.usuario(perms=("ver_resultados", "exportar_visitantes")))
    assert client.get(f"/resultados/{segmento}/{sufixo}").status_code == 404


@ROTAS
@pytest.mark.parametrize("edicao_id", [0, 999_999])
def test_edicao_inexistente_404(client, edicao, rota, edicao_id):
    client.force_login(cenario.usuario(perms=(rota[1],)))
    resposta = client.get(url(rota, edicao_id))
    assert resposta.status_code == 404
    assert "no-store" in resposta["Cache-Control"]


@ROTAS
@pytest.mark.parametrize("metodo", ["post", "put", "delete"])
def test_metodo_que_nao_e_get_405(client, edicao, rota, metodo):
    client.force_login(cenario.usuario(perms=(rota[1],)))
    resposta = getattr(client, metodo)(url(rota, edicao.pk))
    assert resposta.status_code == 405
    assert "no-store" in resposta["Cache-Control"]


@ROTAS
def test_parametros_de_query_sao_ignorados(client, edicao, rota):
    client.force_login(cenario.usuario(perms=(rota[1],)))
    normal = client.get(url(rota, edicao.pk)).content
    assert client.get(url(rota, edicao.pk) + "?edicao_id=0&formato=xlsx").content == normal


def test_urls_das_tres_rotas():
    assert reverse("resultados:operacional", args=[7]) == "/resultados/7/operacional/"
    assert reverse("resultados:visitantes_csv", args=[7]) == "/resultados/7/visitantes.csv"
