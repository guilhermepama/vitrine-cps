"""Admin da votação — fatia F2 (specs/03-credenciamento-votacao.md).

Critérios de aceite fechados aqui (citados em cada teste):
- "Staff não superusuário (grupo digitacao-banca) não vê as ações e recebe
  403 ao chamá-las; anônimo → login" (G15)
- Endpoints, admin de estações: "ValidationError ao mudar edição com tokens;
  apagar com tokens bloqueado" — como mensagem no admin, não 500.
- Ações Abrir/Encerrar pelo admin, com as mensagens de recusa da spec e
  exatamente uma edição selecionada.
"""

from datetime import date

import pytest
from django.contrib.auth.models import Group, Permission, User
from django.contrib.messages import get_messages
from django.urls import reverse

from cadastro.tests import fabricas as cadastro
from votacao.models import EdicaoVotacao, Estacao
from votacao.servicos import abrir_votacao
from votacao.tests import fabricas

pytestmark = pytest.mark.django_db

LISTA_VOTACAO = reverse("admin:votacao_edicaovotacao_changelist")
LISTA_ESTACOES = reverse("admin:votacao_estacao_changelist")


@pytest.fixture
def superusuario(client):
    client.force_login(User.objects.create_superuser("coord", "coord@example.com", "senha-forte-123"))
    return client


@pytest.fixture
def digitacao(client):
    """Staff do grupo digitacao-banca, com todas as permissões dos models da votação:
    mesmo assim não passa — a regra é superusuário, não permissão de model."""
    grupo = Group.objects.create(name="digitacao-banca")
    grupo.permissions.set(Permission.objects.filter(content_type__app_label="votacao"))
    usuario = User.objects.create_user("barbara", "barbara@example.com", "senha-forte-123", is_staff=True)
    usuario.groups.add(grupo)
    client.force_login(usuario)
    return client


def _acao(client, acao, *edicoes):
    return client.post(LISTA_VOTACAO, {"action": acao, "_selected_action": [e.pk for e in edicoes]}, follow=True)


def _mensagens(resposta):
    return [str(m) for m in get_messages(resposta.wsgi_request)]


# --- Abrir/encerrar pelo admin -----------------------------------------------


def test_superusuario_ve_as_acoes_na_lista(superusuario):
    cadastro.edicao()
    resposta = superusuario.get(LISTA_VOTACAO)
    assert resposta.status_code == 200
    assert "Abrir votação" in resposta.text
    assert "Encerrar votação" in resposta.text
    assert "delete_selected" not in resposta.text


def test_superusuario_abre_e_encerra_pela_acao(superusuario):
    evento = cadastro.edicao()

    resposta = _acao(superusuario, "acao_abrir", evento)
    assert _mensagens(resposta) == ["Votação aberta: 2026/2."]
    evento.refresh_from_db()
    assert evento.votacao_aberta_em is not None

    resposta = _acao(superusuario, "acao_encerrar", evento)
    assert _mensagens(resposta) == ["Votação encerrada: 2026/2."]
    evento.refresh_from_db()
    assert evento.votacao_encerrada_em is not None


def test_acao_mostra_a_recusa_do_servico(superusuario):
    ensaio = cadastro.edicao(nome="Ensaio 2026/2", data_evento=date(2026, 10, 22))
    evento = cadastro.edicao()
    abrir_votacao(ensaio.pk)

    resposta = _acao(superusuario, "acao_abrir", evento)

    assert _mensagens(resposta) == ["Já existe uma votação aberta (Ensaio 2026/2). Encerre-a antes de abrir outra."]
    evento.refresh_from_db()
    assert evento.votacao_aberta_em is None


def test_acao_exige_exatamente_uma_edicao(superusuario):
    ensaio = cadastro.edicao(nome="Ensaio 2026/2", data_evento=date(2026, 10, 22))
    evento = cadastro.edicao()

    resposta = _acao(superusuario, "acao_abrir", ensaio, evento)

    assert _mensagens(resposta) == ["Selecione exatamente uma edição."]
    assert not EdicaoVotacao.objects.filter(votacao_aberta_em__isnull=False).exists()


def test_proxy_e_somente_leitura(superusuario):
    evento = cadastro.edicao()
    url = reverse("admin:votacao_edicaovotacao_change", args=[evento.pk])
    assert superusuario.get(url).status_code == 200
    resposta = superusuario.post(url, {"nome": "Outro nome"})
    assert resposta.status_code == 403
    assert superusuario.get(reverse("admin:votacao_edicaovotacao_add")).status_code == 403
    assert superusuario.get(reverse("admin:votacao_edicaovotacao_delete", args=[evento.pk])).status_code == 403
    evento.refresh_from_db()
    assert evento.nome == "2026/2"


# --- G15: só superusuário ------------------------------------------------------


def test_staff_da_digitacao_nao_ve_o_menu_da_votacao(digitacao):
    """Critério: "Staff não superusuário (grupo digitacao-banca) não vê as ações"."""
    resposta = digitacao.get(reverse("admin:index"))
    assert resposta.status_code == 200
    assert LISTA_VOTACAO not in resposta.text
    assert LISTA_ESTACOES not in resposta.text
    assert digitacao.get(LISTA_VOTACAO).status_code == 403


@pytest.mark.parametrize("acao", ["acao_abrir", "acao_encerrar"])
def test_staff_da_digitacao_recebe_403_ao_chamar_a_acao_pela_url(digitacao, acao):
    """Critério: "... e recebe 403 ao chamá-las"."""
    evento = cadastro.edicao()
    if acao == "acao_encerrar":
        abrir_votacao(evento.pk)
    evento.refresh_from_db()
    antes = (evento.votacao_aberta_em, evento.votacao_encerrada_em)

    resposta = digitacao.post(LISTA_VOTACAO, {"action": acao, "_selected_action": [evento.pk]})

    assert resposta.status_code == 403
    evento.refresh_from_db()
    assert (evento.votacao_aberta_em, evento.votacao_encerrada_em) == antes


@pytest.mark.parametrize("url", [LISTA_VOTACAO, LISTA_ESTACOES])
def test_anonimo_vai_para_o_login(client, url):
    """Critério: "anônimo → login"."""
    evento = cadastro.edicao()
    resposta = client.post(url, {"action": "acao_abrir", "_selected_action": [evento.pk]})
    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("admin:login"))
    evento.refresh_from_db()
    assert evento.votacao_aberta_em is None


def test_staff_da_digitacao_nao_mexe_em_estacoes(digitacao):
    estacao = fabricas.estacao()
    assert digitacao.get(LISTA_ESTACOES).status_code == 403
    assert digitacao.get(reverse("admin:votacao_estacao_add")).status_code == 403
    url = reverse("admin:votacao_estacao_change", args=[estacao.pk])
    assert digitacao.post(url, {"nome": "X", "edicao": estacao.edicao_id, "ativa": ""}).status_code == 403
    estacao.refresh_from_db()
    assert (estacao.nome, estacao.ativa) == ("Entrada", True)


# --- Admin de estações ---------------------------------------------------------


def _form_estacao(estacao, **campos):
    dados = {"nome": estacao.nome, "edicao": estacao.edicao_id, "ativa": "on" if estacao.ativa else ""}
    dados.update(campos)
    return dados


def test_superusuario_cadastra_estacao(superusuario):
    evento = cadastro.edicao()
    resposta = superusuario.post(
        reverse("admin:votacao_estacao_add"), {"nome": "Bloco A", "edicao": evento.pk, "ativa": "on"}
    )
    assert resposta.status_code == 302
    assert Estacao.objects.get().edicao == evento


def test_superusuario_desativa_estacao(superusuario):
    estacao = fabricas.estacao()
    url = reverse("admin:votacao_estacao_change", args=[estacao.pk])
    assert superusuario.post(url, _form_estacao(estacao, ativa="")).status_code == 302
    estacao.refresh_from_db()
    assert estacao.ativa is False


def test_mudar_edicao_de_estacao_com_token_vira_erro_no_formulario(superusuario):
    """Critério (Endpoints): ValidationError ao mudar edição com tokens — mensagem no admin, não 500."""
    estacao = fabricas.token().estacao
    original = estacao.edicao_id
    outra = cadastro.edicao(nome="Ensaio 2026/2", data_evento=date(2026, 10, 22))
    url = reverse("admin:votacao_estacao_change", args=[estacao.pk])

    resposta = superusuario.post(url, _form_estacao(estacao, edicao=outra.pk))

    assert resposta.status_code == 200
    assert "Estação que já emitiu token não muda de edição." in resposta.text
    estacao.refresh_from_db()
    assert estacao.edicao_id == original


def test_mudar_edicao_de_estacao_sem_token_e_permitido(superusuario):
    estacao = fabricas.estacao()
    outra = cadastro.edicao(nome="Ensaio 2026/2", data_evento=date(2026, 10, 22))
    url = reverse("admin:votacao_estacao_change", args=[estacao.pk])
    assert superusuario.post(url, _form_estacao(estacao, edicao=outra.pk)).status_code == 302
    estacao.refresh_from_db()
    assert estacao.edicao_id == outra.pk


def test_apagar_estacao_com_token_e_bloqueado_no_admin(superusuario):
    """Critério (Endpoints): apagar com tokens bloqueado — página do admin, não 500."""
    estacao = fabricas.token().estacao
    url = reverse("admin:votacao_estacao_delete", args=[estacao.pk])

    resposta = superusuario.post(url, {"post": "yes"})

    assert resposta.status_code == 200
    assert "protegidos" in resposta.text or "protected" in resposta.text
    assert Estacao.objects.filter(pk=estacao.pk).exists()


def test_apagar_estacao_com_token_pela_acao_em_massa_e_bloqueado(superusuario):
    estacao = fabricas.token().estacao
    resposta = superusuario.post(
        LISTA_ESTACOES, {"action": "delete_selected", "_selected_action": [estacao.pk], "post": "yes"}
    )
    assert resposta.status_code == 200
    assert Estacao.objects.filter(pk=estacao.pk).exists()
