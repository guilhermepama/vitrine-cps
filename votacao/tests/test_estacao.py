"""Página da estação e renovação do QR — fatia F3 (specs/03-credenciamento-votacao.md).

Critérios de aceite fechados aqui (citados em cada teste):
- "QR da estação muda sozinho a cada 45s sem recarregar manualmente" (parte
  do servidor: a renovação devolve QR novo depois de 45 s; o JS da página é
  conferido no ensaio)
- "`/estacao/abc` → 404; estação inativa → 404"
- Todos os de "Acesso à página da estação" (PR #20), inclusive a permissão
  `votacao.operar_estacao` criada por migration e sem acesso a model no admin.
- G3: o segredo do QR não aparece no HTML.
"""

from unittest import mock

import pytest
from django.contrib.auth.models import Group, Permission, User
from django.urls import reverse

from votacao.assinatura import assinar
from votacao.tests import fabricas
from votacao.views_estacao import svg_do_qr

pytestmark = pytest.mark.django_db

AGORA = 1_793_000_000
SENHA = "senha-forte-123"
INEXISTENTE = 999_999
MARCADOR = "MARCADOR-DO-SEGREDO-QR"  # segredo fictício


# Origem pública de teste: o QR nunca sai com o host do request (ADR-006, #32).
URL_PUBLICA = "https://vitrine.teste"


@pytest.fixture(autouse=True)
def url_publica(settings):
    settings.URL_PUBLICA = URL_PUBLICA


@pytest.fixture(autouse=True)
def relogio():
    with mock.patch("votacao.assinatura.agora", return_value=AGORA) as fixo:
        yield fixo


@pytest.fixture
def estacao():
    return fabricas.estacao()


def _operar_estacao():
    return Permission.objects.get(codename="operar_estacao", content_type__app_label="votacao")


def _usuario(nome, grupo=None, **campos):
    usuario = User.objects.create_user(nome, f"{nome}@example.com", SENHA, **campos)
    if grupo:
        usuario.groups.add(grupo)
    return usuario


@pytest.fixture
def grupo_estacao():
    grupo = Group.objects.create(name="estação")
    grupo.permissions.add(_operar_estacao())
    return grupo


@pytest.fixture
def operador(client, grupo_estacao):
    """Conta do notebook da estação: staff, só no grupo "estação"."""
    client.force_login(_usuario("estacao1", grupo_estacao, is_staff=True))
    return client


@pytest.fixture
def digitacao(client):
    """Staff do grupo digitacao-banca, com todas as permissões de model da votação,
    menos a de operar a estação."""
    grupo = Group.objects.create(name="digitacao-banca")
    grupo.permissions.set(Permission.objects.filter(content_type__app_label="votacao").exclude(codename="operar_estacao"))
    client.force_login(_usuario("barbara", grupo, is_staff=True))
    return client


def _pagina(estacao_id):
    return reverse("votacao:estacao", args=[estacao_id])


def _renovacao(estacao_id):
    return reverse("votacao:estacao_qr", args=[estacao_id])


def _corpo_404(client):
    """Corpo de referência: estação inexistente, vista por quem tem a permissão."""
    operador = _usuario("referencia", is_staff=True)
    operador.user_permissions.add(_operar_estacao())
    client.force_login(operador)
    resposta = client.get(_pagina(INEXISTENTE))
    client.logout()
    assert resposta.status_code == 404
    return resposta.content


def _sem_qr(resposta):
    corpo = resposta.content.decode()
    return "<svg" not in corpo and "w=" not in corpo and "sig=" not in corpo


# --- Permissão (migration) ---------------------------------------------------


def test_permissao_operar_estacao_existe_com_o_nome_da_spec():
    permissao = _operar_estacao()
    assert permissao.name == "Pode operar a página da estação"
    assert permissao.content_type.model == "estacao"


def test_permissao_nao_da_acesso_a_nenhum_model_no_admin(client, grupo_estacao):
    client.force_login(_usuario("estacao1", grupo_estacao, is_staff=True))
    indice = client.get(reverse("admin:index"))
    assert indice.status_code == 200
    assert "/admin/votacao/" not in indice.text
    for rota in ["admin:votacao_estacao_changelist", "admin:votacao_edicaovotacao_changelist", "admin:votacao_estacao_add"]:
        assert client.get(reverse(rota)).status_code == 403


# --- Anônimo e sessão inválida → login do admin -------------------------------


@pytest.mark.parametrize("rota", [_pagina, _renovacao])
def test_anonimo_vai_para_o_login_do_admin_sem_qr(client, estacao, rota):
    resposta = client.get(rota(estacao.pk))
    assert resposta.status_code == 302
    assert resposta["Location"] == f"{reverse('admin:login')}?next=/estacao/{estacao.pk}"
    assert _sem_qr(resposta)


def test_anonimo_em_estacao_inexistente_recebe_o_mesmo_302(client, estacao):
    existente = client.get(_pagina(estacao.pk))
    inexistente = client.get(_pagina(INEXISTENTE))
    assert inexistente.status_code == 302
    assert inexistente["Location"] == f"{reverse('admin:login')}?next=/estacao/{INEXISTENTE}"
    assert inexistente.content == existente.content


def test_staff_inativo_nao_loga_e_com_sessao_antiga_e_tratado_como_anonimo(client, estacao, grupo_estacao):
    usuario = _usuario("estacao1", grupo_estacao, is_staff=True, is_active=False)
    client.post(reverse("admin:login"), {"username": "estacao1", "password": SENHA})
    assert "_auth_user_id" not in client.session

    client.force_login(usuario)  # sessão de antes da desativação
    for rota in [_pagina, _renovacao]:
        resposta = client.get(rota(estacao.pk))
        assert resposta.status_code == 302
        assert resposta["Location"].startswith(reverse("admin:login"))
        assert _sem_qr(resposta)


# --- Logado sem staff ou sem permissão → 404 igual ao da inexistente ----------


@pytest.mark.parametrize("rota", [_pagina, _renovacao])
def test_logado_sem_staff_recebe_404_igual_ao_da_inexistente(client, estacao, rota):
    referencia = _corpo_404(client)
    client.force_login(_usuario("visitante"))
    resposta = client.get(rota(estacao.pk))
    assert resposta.status_code == 404
    assert resposta.content == referencia
    assert _sem_qr(resposta)


@pytest.mark.parametrize("rota", [_pagina, _renovacao])
def test_staff_sem_permissao_recebe_404_igual_ao_da_inexistente(digitacao, estacao, rota):
    resposta = digitacao.get(rota(estacao.pk))
    assert resposta.status_code == 404
    assert _sem_qr(resposta)
    sem_staff = User.objects.create_user("sem_staff", "sem_staff@example.com", SENHA)
    digitacao.force_login(sem_staff)
    assert digitacao.get(rota(estacao.pk)).content == resposta.content
    assert resposta.content == _corpo_404(digitacao)


def test_permissao_sem_staff_nao_loga_e_com_sessao_antiga_recebe_404(client, estacao, grupo_estacao):
    usuario = _usuario("estacao1", grupo_estacao)
    client.post(reverse("admin:login"), {"username": "estacao1", "password": SENHA})
    assert "_auth_user_id" not in client.session

    referencia = _corpo_404(client)
    client.force_login(usuario)
    for rota in [_pagina, _renovacao]:
        resposta = client.get(rota(estacao.pk))
        assert resposta.status_code == 404
        assert resposta.content == referencia


def test_staff_sem_permissao_em_estacao_inexistente_tem_o_mesmo_404(digitacao, estacao):
    assert digitacao.get(_pagina(estacao.pk)).content == digitacao.get(_pagina(INEXISTENTE)).content


# --- Operador da estação ------------------------------------------------------


def test_operador_ve_o_qr_da_janela_assinada(operador, estacao):
    resposta = operador.get(_pagina(estacao.pk))
    assert resposta.status_code == 200
    url = f"{URL_PUBLICA}/entrar?w={estacao.pk}:{AGORA}&sig={assinar(estacao.pk, AGORA)}"
    assert svg_do_qr(url) in resposta.text
    assert estacao.nome in resposta.text


@pytest.mark.parametrize("rota", [_pagina, _renovacao])
def test_qr_sai_com_https_atras_do_proxy(operador, estacao, rota, settings):
    """O QR usa a URL_PUBLICA seja qual for o Host e o X-Forwarded-Proto."""
    settings.URL_PUBLICA = "https://vitrine.exemplo.com.br"
    # Valor do config/settings.py com DEBUG desligado (produção e CI); fixado
    # aqui para o teste não depender do DJANGO_DEBUG do .env local.
    settings.SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    settings.ALLOWED_HOSTS = ["interno.coolify", "testserver"]
    esperado = f"https://vitrine.exemplo.com.br/entrar?w={estacao.pk}:{AGORA}&sig={assinar(estacao.pk, AGORA)}"
    # Host interno e esquema http no proxy: nada disso vai para o QR.
    for cabecalhos in (
        {"HTTP_HOST": "interno.coolify", "HTTP_X_FORWARDED_PROTO": "http"},
        {"HTTP_HOST": "testserver", "HTTP_X_FORWARDED_PROTO": "https"},
        {"HTTP_HOST": "interno.coolify"},
    ):
        resposta = operador.get(rota(estacao.pk), **cabecalhos)
        assert resposta.status_code == 200
        assert svg_do_qr(esperado) in resposta.content.decode()
        assert "interno.coolify" not in resposta.content.decode()


def test_operador_loga_pelo_login_do_admin(client, estacao, grupo_estacao):
    _usuario("estacao1", grupo_estacao, is_staff=True)
    client.post(reverse("admin:login"), {"username": "estacao1", "password": SENHA})
    assert client.get(_pagina(estacao.pk)).status_code == 200


def test_superusuario_ve_a_estacao(client, estacao):
    client.force_login(User.objects.create_superuser("coord", "coord@example.com", SENHA))
    assert client.get(_pagina(estacao.pk)).status_code == 200


def test_pagina_renova_por_fetch_e_tem_meta_refresh_de_reserva(operador, estacao):
    corpo = operador.get(_pagina(estacao.pk)).text
    assert f'data-renovar="{_renovacao(estacao.pk)}"' in corpo
    assert 'data-intervalo="45"' in corpo
    assert "fetch(" in corpo
    assert "visibilitychange" in corpo
    assert '<meta http-equiv="refresh" content="45">' in corpo


@pytest.mark.parametrize("rota", [_pagina, _renovacao])
def test_resposta_da_estacao_sem_cache(operador, estacao, rota):
    assert "no-store" in operador.get(rota(estacao.pk))["Cache-Control"]


def test_anonimo_tambem_recebe_no_store(client, estacao):
    assert "no-store" in client.get(_pagina(estacao.pk))["Cache-Control"]


@pytest.mark.parametrize("rota", [_pagina, _renovacao])
def test_estacao_inexistente_ou_inativa_404(operador, estacao, rota):
    assert operador.get(rota(INEXISTENTE)).status_code == 404
    inativa = fabricas.estacao(estacao.edicao, nome="Desligada", ativa=False)
    resposta = operador.get(rota(inativa.pk))
    assert resposta.status_code == 404
    assert resposta.content == operador.get(rota(INEXISTENTE)).content


@pytest.mark.parametrize("caminho", ["/estacao/abc", "/estacao/-1", "/estacao/1.5", "/estacao/abc/qr"])
def test_id_nao_inteiro_404(operador, caminho):
    assert operador.get(caminho).status_code == 404


def test_id_fora_da_faixa_404(operador):
    assert operador.get("/estacao/99999999999999999999").status_code == 404


@pytest.mark.parametrize("rota", [_pagina, _renovacao])
def test_post_nao_permitido_e_sem_cache(operador, estacao, rota):
    resposta = operador.post(rota(estacao.pk))
    assert resposta.status_code == 405
    assert "no-store" in resposta["Cache-Control"]


# --- Renovação do QR ------------------------------------------------------------


def test_renovacao_devolve_so_o_svg(operador, estacao):
    resposta = operador.get(_renovacao(estacao.pk))
    assert resposta.status_code == 200
    assert resposta["Content-Type"].startswith("image/svg+xml")
    url = f"{URL_PUBLICA}/entrar?w={estacao.pk}:{AGORA}&sig={assinar(estacao.pk, AGORA)}"
    assert resposta.content.decode() == svg_do_qr(url)


def test_qr_muda_a_cada_45s(operador, estacao, relogio):
    primeiro = operador.get(_renovacao(estacao.pk)).content
    assert operador.get(_renovacao(estacao.pk)).content == primeiro
    relogio.return_value = AGORA + 45
    segundo = operador.get(_renovacao(estacao.pk)).content
    assert segundo != primeiro
    url = f"{URL_PUBLICA}/entrar?w={estacao.pk}:{AGORA + 45}&sig={assinar(estacao.pk, AGORA + 45)}"
    assert segundo.decode() == svg_do_qr(url)


def test_estacao_desativada_durante_o_evento_para_de_renovar(operador, estacao):
    assert operador.get(_renovacao(estacao.pk)).status_code == 200
    estacao.ativa = False
    estacao.save()
    assert operador.get(_renovacao(estacao.pk)).status_code == 404


def test_qr_de_estacoes_diferentes_e_diferente(operador, estacao):
    outra = fabricas.estacao(edicao_=estacao.edicao, nome="Saída")
    assert operador.get(_renovacao(estacao.pk)).content != operador.get(_renovacao(outra.pk)).content


# --- Segredo -------------------------------------------------------------------------


def test_segredo_nunca_aparece_no_html(operador, estacao, settings):
    settings.QR_HMAC_SECRET = MARCADOR
    for rota in [_pagina, _renovacao]:
        resposta = operador.get(rota(estacao.pk))
        assert resposta.status_code == 200
        assert MARCADOR.encode() not in resposta.content
