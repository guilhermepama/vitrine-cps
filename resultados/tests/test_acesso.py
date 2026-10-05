"""Acesso e validação do ranking (specs/04-resultados.md, fatia 2).

Critérios de aceite fechados aqui (rota do ranking; operacional e CSV ficam
para a fatia 3):
- Usuário anônimo → redirect para o login
- Autenticado não admin (sem `is_staff`) com `ver_resultados` e
  `exportar_visitantes` → 403
- Admin sem permissão (grupo `digitacao-banca`) → 403
- `edicao_id` não inteiro (`abc`, `-1`, `1.5`) → 404
- `edicao_id` inteiro sem edição (`0`, inexistente) → 404; POST → 405
- App não tem migration que crie tabela (só o model de permissões)
- `resultados/urls.py` declara `app_name = "resultados"`
"""

import pytest
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.urls import reverse

from banca.sinais import GRUPO_DIGITACAO
from resultados import urls
from resultados.models import PermissaoResultados
from resultados.tests import cenario

pytestmark = pytest.mark.django_db


@pytest.fixture
def edicao():
    return cenario.edicao({"DSM": [("Agenda", 3, 8)]})[0]


def url(edicao_id):
    return reverse("resultados:ranking", args=[edicao_id])


def test_anonimo_vai_para_o_login_do_admin(client, edicao):
    resposta = client.get(url(edicao.pk))
    assert resposta.status_code == 302
    assert resposta.url == f"{reverse('admin:login')}?next={url(edicao.pk)}"


def test_nao_admin_com_as_duas_permissoes_recebe_403(client, edicao):
    client.force_login(cenario.usuario(staff=False, perms=("ver_resultados", "exportar_visitantes")))
    assert client.get(url(edicao.pk)).status_code == 403


def test_inativo_nao_ve(client, edicao):
    """O backend padrão derruba a sessão de quem foi desativado: vira anônimo."""
    u = cenario.usuario()
    client.force_login(u)
    u.is_active = False
    u.save()
    assert client.get(url(edicao.pk)).status_code == 302


def test_admin_do_grupo_digitacao_banca_recebe_403_sem_cache(client, edicao):
    u = cenario.usuario(perms=())
    u.groups.add(Group.objects.get(name=GRUPO_DIGITACAO))
    client.force_login(u)
    resposta = client.get(url(edicao.pk))
    assert resposta.status_code == 403
    assert "no-store" in resposta["Cache-Control"]


def test_admin_so_com_exportar_visitantes_recebe_403(client, edicao):
    client.force_login(cenario.usuario(perms=("exportar_visitantes",)))
    assert client.get(url(edicao.pk)).status_code == 403


def test_admin_com_ver_resultados_ve_a_pagina_sem_cache(client, edicao):
    client.force_login(cenario.usuario())
    resposta = client.get(url(edicao.pk))
    assert resposta.status_code == 200
    assert "no-store" in resposta["Cache-Control"]


def test_superusuario_ve_a_pagina(client, edicao):
    client.force_login(cenario.usuario(staff=True, perms=(), is_superuser=True))
    assert client.get(url(edicao.pk)).status_code == 200


def test_403_vem_antes_do_404(client):
    """Sem a permissão, edição inexistente também dá 403: não revela ids."""
    client.force_login(cenario.usuario(perms=()))
    assert client.get(url(999_999)).status_code == 403


@pytest.mark.parametrize("segmento", ["abc", "-1", "1.5"])
def test_segmento_nao_inteiro_e_rota_inexistente(client, edicao, segmento):
    client.force_login(cenario.usuario())
    assert client.get(f"/resultados/{segmento}/").status_code == 404


@pytest.mark.parametrize("edicao_id", [0, 999_999])
def test_edicao_inexistente_404(client, edicao, edicao_id):
    client.force_login(cenario.usuario())
    resposta = client.get(url(edicao_id))
    assert resposta.status_code == 404
    assert "no-store" in resposta["Cache-Control"]


@pytest.mark.parametrize("metodo", ["post", "put", "delete"])
def test_metodo_que_nao_e_get_405(client, edicao, metodo):
    client.force_login(cenario.usuario())
    resposta = getattr(client, metodo)(url(edicao.pk))
    assert resposta.status_code == 405
    assert "no-store" in resposta["Cache-Control"]


def test_parametros_de_query_sao_ignorados(client, edicao):
    client.force_login(cenario.usuario())
    normal = client.get(url(edicao.pk)).content
    assert client.get(url(edicao.pk) + "?edicao_id=0&turma=1&formato=csv").content == normal


def test_permissoes_criadas_pela_migration_sem_tabela():
    codenames = set(
        Permission.objects.filter(content_type__app_label="resultados").values_list("codename", flat=True)
    )
    assert codenames == {"ver_resultados", "exportar_visitantes"}
    assert PermissaoResultados._meta.managed is False
    assert PermissaoResultados._meta.db_table not in connection.introspection.table_names()


def test_urls_do_app():
    assert urls.app_name == "resultados"
    assert reverse("resultados:ranking", args=[7]) == "/resultados/7/"
