"""Admin de critérios e jurados (spec 06, fatia 2)."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from banca.models import Criterio, Jurado
from banca.sinais import GRUPO_DIGITACAO
from banca.tests import fabricas
from cadastro.tests import fabricas as cadastro

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def admin_client(client):
    client.force_login(User.objects.create_superuser("coord", "coord@example.com", "senha-forte-123"))
    return client


@pytest.fixture
def digitacao(client):
    usuario = User.objects.create_user("barbara", "b@example.com", "senha-forte-123", is_staff=True)
    usuario.groups.add(Group.objects.get(name=GRUPO_DIGITACAO))
    client.force_login(usuario)
    return client


def _url(modelo, acao, *args):
    return reverse(f"admin:banca_{modelo}_{acao}", args=args)


# --- Critérios --------------------------------------------------------------------------


def test_superusuario_cria_criterio_antes_de_abrir(admin_client):
    edicao = cadastro.edicao()
    resposta = admin_client.post(_url("criterio", "add"), {"edicao": edicao.pk, "nome": "Inovação", "apoio": "", "ordem": 1})
    assert resposta.status_code == 302
    assert Criterio.objects.filter(edicao=edicao, nome="Inovação").exists()


def test_criar_criterio_em_edicao_aberta_volta_com_erro(admin_client):
    edicao = fabricas.cenario()[0]
    resposta = admin_client.post(_url("criterio", "add"), {"edicao": edicao.pk, "nome": "Novo", "apoio": "", "ordem": 9})
    assert resposta.status_code == 200
    assert "não mudam depois de aberta a votação" in resposta.content.decode()
    assert not Criterio.objects.filter(nome="Novo").exists()


def test_criterio_de_edicao_aberta_e_so_leitura(admin_client):
    edicao = fabricas.cenario()[0]
    criterio = Criterio.objects.filter(edicao=edicao).first()
    resposta = admin_client.post(_url("criterio", "change", criterio.pk), {"edicao": edicao.pk, "nome": "Mudou", "apoio": "", "ordem": 1})
    assert resposta.status_code == 403
    assert admin_client.get(_url("criterio", "delete", criterio.pk)).status_code == 403
    criterio.refresh_from_db()
    assert criterio.nome == "Critério 1"


def test_sem_apagar_em_lote(admin_client):
    for modelo in ("criterio", "jurado"):
        resposta = admin_client.get(_url(modelo, "changelist"))
        assert "delete_selected" not in resposta.content.decode()


# --- Jurados ----------------------------------------------------------------------------


def _dados_jurado(edicao, *turmas, nome="Ana"):
    return {"edicao": edicao.pk, "nome": nome, "turmas": [t.pk for t in turmas]}


def test_superusuario_cria_jurado_com_turmas_da_edicao(admin_client):
    edicao, turma, _ = fabricas.cenario()
    resposta = admin_client.post(_url("jurado", "add"), _dados_jurado(edicao, turma))
    assert resposta.status_code == 302
    assert list(Jurado.objects.get(nome="Ana").turmas.all()) == [turma]


def test_turma_de_outra_edicao_e_recusada(admin_client):
    edicao, turma, _ = fabricas.cenario()
    alheia = cadastro.turma(cadastro.edicao(nome="Ensaio 2026/2"), cadastro.curso("GTUR"))
    resposta = admin_client.post(_url("jurado", "add"), _dados_jurado(edicao, turma, alheia))
    assert resposta.status_code == 200
    assert "da edição dele" in resposta.content.decode()
    assert not Jurado.objects.exists()


def test_rotulo_da_turma_leva_a_edicao(admin_client):
    edicao = fabricas.cenario()[0]
    assert f"{edicao} · DSM" in admin_client.get(_url("jurado", "add")).content.decode()


@pytest.fixture
def jurado_com_avaliacao():
    edicao, turma, projetos = fabricas.cenario()
    jurado = fabricas.jurado(edicao, turma)
    fabricas.avaliar(jurado, projetos[0], [7, 8])
    return edicao, turma, jurado


def test_jurado_com_avaliacao_nao_perde_a_turma(admin_client, jurado_com_avaliacao):
    edicao, turma, jurado = jurado_com_avaliacao
    outra = cadastro.turma(edicao, cadastro.curso("GTUR"))
    resposta = admin_client.post(_url("jurado", "change", jurado.pk), _dados_jurado(edicao, outra))
    assert resposta.status_code == 200
    assert "não perde a turma" in resposta.content.decode()
    assert list(Jurado.objects.get(pk=jurado.pk).turmas.all()) == [turma]


def test_jurado_com_avaliacao_nao_muda_de_edicao(admin_client, jurado_com_avaliacao):
    _, _, jurado = jurado_com_avaliacao
    outra = cadastro.edicao(nome="Ensaio 2026/2")
    turma_outra = cadastro.turma(outra, cadastro.curso("GTUR"))
    resposta = admin_client.post(_url("jurado", "change", jurado.pk), _dados_jurado(outra, turma_outra))
    assert resposta.status_code == 200
    assert "não muda de edição" in resposta.content.decode()


def test_jurado_com_avaliacao_pode_ganhar_turma_e_mudar_nome(admin_client, jurado_com_avaliacao):
    edicao, turma, jurado = jurado_com_avaliacao
    outra = cadastro.turma(edicao, cadastro.curso("GTUR"))
    resposta = admin_client.post(_url("jurado", "change", jurado.pk), _dados_jurado(edicao, turma, outra, nome="Ana B."))
    assert resposta.status_code == 302
    assert Jurado.objects.get(pk=jurado.pk).turmas.count() == 2


def test_jurado_com_avaliacao_nao_e_apagado(admin_client, jurado_com_avaliacao):
    jurado = jurado_com_avaliacao[2]
    assert admin_client.get(_url("jurado", "delete", jurado.pk)).status_code == 403


def test_jurado_sem_avaliacao_pode_ser_apagado(admin_client):
    edicao, turma, _ = fabricas.cenario()
    jurado = fabricas.jurado(edicao, turma)
    assert admin_client.post(_url("jurado", "delete", jurado.pk), {"post": "yes"}).status_code == 302
    assert not Jurado.objects.exists()


# --- Grupo de digitação e anônimo ----------------------------------------------------------


def test_digitacao_ve_mas_nao_altera(digitacao):
    edicao = cadastro.edicao()
    criterio = Criterio.objects.create(edicao=edicao, nome="C", ordem=1)
    jurado = Jurado.objects.create(edicao=edicao, nome="Ana")
    assert digitacao.get(_url("criterio", "changelist")).status_code == 200
    assert digitacao.get(_url("jurado", "changelist")).status_code == 200
    assert digitacao.get(_url("criterio", "add")).status_code == 403
    assert digitacao.get(_url("jurado", "add")).status_code == 403
    dados = {"edicao": edicao.pk, "nome": "Mudou", "apoio": "", "ordem": 1}
    assert digitacao.post(_url("criterio", "change", criterio.pk), dados).status_code == 403
    assert digitacao.post(_url("jurado", "change", jurado.pk), _dados_jurado(edicao, nome="X")).status_code == 403
    assert digitacao.get(_url("jurado", "delete", jurado.pk)).status_code == 403
    criterio.refresh_from_db()
    assert criterio.nome == "C"


def test_anonimo_vai_para_o_login(client):
    resposta = client.get(_url("criterio", "changelist"))
    assert resposta.status_code == 302 and "/login/" in resposta["Location"]
