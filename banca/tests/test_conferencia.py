"""Conferência da banca e reabertura da digitação (spec 06, fatia 5)."""

import os
import re
import subprocess
import sys
import threading
import time

import pytest
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages import get_messages
from django.db import connection, connections, transaction
from django.test import Client
from django.test.client import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone

from banca import conferencia as modulo
from banca.models import Avaliacao, Jurado
from banca.sinais import GRUPO_DIGITACAO
from banca.tests import fabricas
from cadastro.models import Edicao, Projeto
from cadastro.tests import fabricas as cadastro
from votacao.servicos import encerrar_votacao

pytestmark = pytest.mark.django_db
User = get_user_model()
ADD = reverse("admin:banca_avaliacao_add")


def _url(edicao, **params):
    url = reverse("admin:banca_jurado_conferencia", args=[edicao.pk])
    return url + ("?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else "")


def _staff(username, *permissoes, staff=True):
    usuario = User.objects.create_user(username, f"{username}@example.com", "senha-forte-123", is_staff=staff)
    for codigo in permissoes:
        usuario.user_permissions.add(Permission.objects.get(content_type__app_label="banca", codename=codigo))
    return usuario


@pytest.fixture
def renan():
    return _staff("renan", "concluir_conferencia")


@pytest.fixture
def conferente(client, renan):
    client.force_login(renan)
    return client


def _edicao(projetos=3, jurados=("Ana", "Bia"), encerrar=True, nome="2026/2", sigla="DSM"):
    edicao, turma, lista = fabricas.cenario(criterios=2, projetos=projetos, nome=nome, sigla=sigla)
    js = [fabricas.jurado(edicao, turma, nome=n) for n in jurados]
    if encerrar:
        assert encerrar_votacao(edicao.pk) is None
        edicao.refresh_from_db()
    return edicao, turma, lista, js


def _avaliar_todos(jurados, projetos, usuario=None):
    return [fabricas.avaliar(j, p, [7, 8], usuario) for j in jurados for p in projetos]


def _mensagens(resposta):
    return [str(m) for m in get_messages(resposta.wsgi_request)]


def _linhas(resposta):
    return re.findall(r'<tr class="avaliacao">(.*?)</tr>', resposta.content.decode(), re.S)


def _versao_da_pagina(client, edicao):
    """A versão que o formulário da página traz, lida de um GET de verdade."""
    achado = re.search(r'name="versao" value="([0-9a-f]+)"', client.get(_url(edicao)).content.decode())
    return achado.group(1) if achado else ""


def _concluir(client, edicao, acao="concluir", versao=None):
    dados = {"acao": acao}
    if acao == "concluir":
        dados["versao"] = _versao_da_pagina(client, edicao) if versao is None else versao
    return client.post(_url(edicao), dados)


# --- Amostra -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "total, esperado", [(0, 0), (3, 3), (10, 10), (11, 10), (50, 10), (51, 11), (55, 11), (56, 12), (100, 20)]
)
def test_tamanho_da_amostra(total, esperado):
    assert modulo.tamanho_da_amostra(total) == esperado


def test_amostra_independe_da_ordem_de_entrada_e_muda_com_o_conjunto():
    ids = list(range(1, 61))
    amostra = modulo.sortear_amostra(7, ids)
    assert len(amostra) == 12 and len(set(amostra)) == 12 and set(amostra) <= set(ids)
    assert modulo.sortear_amostra(7, list(reversed(ids))) == amostra
    assert modulo.sortear_amostra(8, ids) != amostra
    assert modulo.sortear_amostra(7, ids + [61]) != amostra


def test_mesma_amostra_em_outro_processo():
    ids = list(range(3, 300, 7))
    codigo = (
        "import django; django.setup(); from banca.conferencia import sortear_amostra; "
        f"print(sortear_amostra(5, {ids!r}))"
    )
    env = {**os.environ, "PYTHONHASHSEED": "123", "DJANGO_SETTINGS_MODULE": "config.settings"}
    saida = subprocess.run([sys.executable, "-c", codigo], env=env, capture_output=True, text=True, check=True)
    assert saida.stdout.strip() == str(modulo.sortear_amostra(5, ids))


def test_pagina_mostra_a_amostra_e_a_mesma_em_duas_aberturas(conferente):
    edicao, _, projetos, jurados = _edicao(projetos=6)
    avaliacoes = _avaliar_todos(jurados, projetos)  # 12 → amostra de 10
    primeira = conferente.get(_url(edicao))
    assert primeira.status_code == 200
    assert len(_linhas(primeira)) == 10
    assert _linhas(conferente.get(_url(edicao))) == _linhas(primeira)
    sorteadas = set(modulo.sortear_amostra(edicao.pk, [a.pk for a in avaliacoes]))
    mostradas = {(a.jurado.nome, a.projeto_id) for a in avaliacoes if a.pk in sorteadas}
    html = "".join(_linhas(primeira))
    for nome, projeto_id in mostradas:
        assert f"<td>{nome}</td><td>#{projeto_id} — " in html


def test_menos_de_10_avaliacoes_mostra_todas(conferente):
    edicao, _, projetos, jurados = _edicao(projetos=2)
    _avaliar_todos(jurados, projetos)
    assert len(_linhas(conferente.get(_url(edicao)))) == 4


def test_amostra_de_20_por_cento_arredondada_para_cima(conferente):
    edicao, _, projetos, jurados = _edicao(projetos=17, jurados=("Ana", "Bia", "Caio"))
    _avaliar_todos(jurados, projetos)  # 51 → 11
    assert len(_linhas(conferente.get(_url(edicao)))) == 11


def test_linha_mostra_jurado_projeto_digitador_e_notas_na_ordem(conferente):
    edicao, _, projetos, jurados = _edicao(projetos=1, jurados=("Ana",))
    fabricas.avaliar(jurados[0], projetos[0], [6.5, 9])
    html = conferente.get(_url(edicao)).content.decode()
    titulo = projetos[0].titulo
    assert f"<td>Ana</td><td>#{projetos[0].pk} — {titulo}</td><td>barbara</td><td>6,5</td><td>9,0</td>" in html
    assert html.index("1. Critério 1") < html.index("2. Critério 2")


def test_filtro_por_digitador_lista_todas_dele(conferente):
    edicao, _, projetos, jurados = _edicao(projetos=12)
    carla = fabricas.digitador("carla")
    _avaliar_todos(jurados[:1], projetos)  # 12 da barbara
    _avaliar_todos(jurados[1:], projetos, carla)  # 12 da carla: mais que uma amostra
    barbara = User.objects.get(username="barbara")
    linhas = _linhas(conferente.get(_url(edicao, digitador=carla.pk)))
    assert len(linhas) == 12 and all("<td>carla</td>" in linha for linha in linhas)
    assert len(_linhas(conferente.get(_url(edicao, digitador=barbara.pk)))) == 12
    pagina = conferente.get(_url(edicao)).content.decode()
    assert f'href="?digitador={carla.pk}">carla (12)</a>' in pagina


@pytest.mark.parametrize("valor", ["abc", "", "١", "9" * 19, "9" * 5000])
def test_digitador_invalido_volta_com_mensagem(conferente, valor):
    edicao, *_ = _edicao()
    resposta = conferente.get(_url(edicao), {"digitador": valor})
    assert resposta.status_code == 302 and resposta.url == _url(edicao)
    assert _mensagens(resposta)[-1:] == ["Digitador inválido."]


def test_digitador_com_18_digitos_e_aceito_sem_linhas(conferente):
    edicao, _, projetos, jurados = _edicao()
    _avaliar_todos(jurados, projetos)
    resposta = conferente.get(_url(edicao), {"digitador": "9" * 18})
    assert resposta.status_code == 200 and _linhas(resposta) == []


def test_sem_avaliacoes_linha_vazia_ocupa_todas_as_colunas(conferente):
    edicao, *_ = _edicao()  # 2 critérios
    assert '<td colspan="5">Nenhuma avaliação.</td>' in conferente.get(_url(edicao)).content.decode()


# --- Cobertura -----------------------------------------------------------------------------


def test_cobertura_por_jurado_e_por_turma(conferente):
    edicao, turma, projetos, (ana, bia) = _edicao(projetos=3)
    cadastro.projeto(turma, titulo="Não publicado")
    fabricas.avaliar(ana, projetos[0], [7, 7])
    fabricas.avaliar(bia, projetos[0], [7, 7])
    fabricas.avaliar(ana, projetos[1], [7, 7])
    html = conferente.get(_url(edicao)).content.decode()
    assert '<tr class="cobertura-jurado"><td>Ana</td><td>2 / 3</td></tr>' in html
    assert '<tr class="cobertura-jurado"><td>Bia</td><td>1 / 3</td></tr>' in html
    sem = re.search(r'<ul class="sem-avaliacao">(.*?)</ul>', html).group(1)
    assert sem == f"<li>#{projetos[2].pk} — {projetos[2].titulo}</li>"
    incompletos = re.search(r'<ul class="incompletos">(.*?)</ul>', html).group(1)
    assert incompletos == f"<li>#{projetos[1].pk} — {projetos[1].titulo} (1 de 2)</li>"
    assert "Não publicado" not in html
    assert "1 projeto publicado sem nenhuma avaliação" in html  # aviso antes do botão
    assert html.index("sem nenhuma avaliação. A turma") < html.index('value="concluir"')


def test_cobertura_ignora_outra_edicao(conferente):
    edicao, *_ = _edicao(projetos=1)
    outra, turma_outra, proj_outra, jur_outra = _edicao(projetos=1, jurados=("Zeca",), nome="Ensaio", sigla="ADS")
    fabricas.avaliar(jur_outra[0], proj_outra[0], [5, 5])
    html = conferente.get(_url(edicao)).content.decode()
    assert "Zeca" not in html and f"#{proj_outra[0].pk} —" not in html


def test_numero_fixo_de_consultas(conferente):
    def contar(edicao):
        with CaptureQueriesContext(connection) as capturadas:
            assert conferente.get(_url(edicao)).status_code == 200
        return len(capturadas)

    pequena, _, projetos, jurados = _edicao(projetos=1, jurados=("Ana",), nome="Pequena", sigla="P")
    _avaliar_todos(jurados, projetos)
    grande, turma, projetos, jurados = _edicao(projetos=8, jurados=("Ana", "Bia", "Caio"), nome="Grande")
    outra_turma = cadastro.turma(grande, cadastro.curso("GTUR"))
    jurados[0].turmas.add(outra_turma)
    cadastro.projeto(outra_turma, titulo="Turismo", status=Projeto.Status.PUBLICADO)
    _avaliar_todos(jurados, projetos)
    assert contar(pequena) == contar(grande)


# --- Concluir ------------------------------------------------------------------------------


def test_concluir_valido_preenche_e_registra(conferente, renan):
    edicao, _, projetos, jurados = _edicao()
    _avaliar_todos(jurados, projetos)
    antes = timezone.now()
    resposta = _concluir(conferente, edicao)
    assert resposta.status_code == 302 and resposta.url == _url(edicao)
    assert _mensagens(resposta)[-1:] == ["Conferência concluída."]
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is not None and edicao.banca_conferida_em >= antes
    log = LogEntry.objects.get(content_type=ContentType.objects.get_for_model(Edicao), object_id=str(edicao.pk))
    assert log.user == renan and log.change_message == "Conferência da banca concluída por renan"


def test_quem_digitou_nao_conclui(client):
    edicao, _, projetos, jurados = _edicao()
    renan = _staff("renan", "concluir_conferencia")
    _avaliar_todos(jurados[:1], projetos)
    fabricas.avaliar(jurados[1], projetos[0], [5, 5], renan)
    client.force_login(renan)
    resposta = _concluir(client, edicao)
    assert resposta.status_code == 302
    assert _mensagens(resposta)[-1:] == [modulo.QUEM_DIGITOU]
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None


def test_quem_so_corrigiu_conclui(conferente, renan):
    edicao, _, projetos, jurados = _edicao()
    avaliacao = _avaliar_todos(jurados, projetos)[0]
    avaliacao.alterado_por, avaliacao.alterado_em = renan, timezone.now()
    avaliacao.save(update_fields=["alterado_por", "alterado_em"])
    _concluir(conferente, edicao)
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is not None


def test_recusa_com_votacao_nao_encerrada(conferente):
    edicao, _, projetos, jurados = _edicao(encerrar=False)
    _avaliar_todos(jurados, projetos)
    resposta = _concluir(conferente, edicao)
    assert _mensagens(resposta)[-1:] == [modulo.NAO_ENCERRADA]
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None


def test_recusa_sem_avaliacoes(conferente):
    edicao, *_ = _edicao()
    resposta = _concluir(conferente, edicao)
    assert _mensagens(resposta)[-1:] == [modulo.SEM_AVALIACOES]
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None


def test_recusa_ja_conferida_sem_mudar(conferente):
    edicao, _, projetos, jurados = _edicao()
    _avaliar_todos(jurados, projetos)
    _concluir(conferente, edicao)
    edicao.refresh_from_db()
    primeira = edicao.banca_conferida_em
    resposta = _concluir(conferente, edicao)
    assert _mensagens(resposta)[-1:] == [modulo.JA_CONFERIDA]
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em == primeira
    assert LogEntry.objects.count() == 1


def test_acao_invalida(conferente):
    edicao, _, projetos, jurados = _edicao()
    _avaliar_todos(jurados, projetos)
    resposta = _concluir(conferente, edicao, acao="apagar")
    assert resposta.status_code == 302 and _mensagens(resposta)[-1:] == ["Ação inválida."]
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None


def test_post_sem_csrf_403(renan):
    edicao, _, projetos, jurados = _edicao()
    _avaliar_todos(jurados, projetos)
    cliente = Client(enforce_csrf_checks=True)
    cliente.force_login(renan)
    for acao in ("concluir", "reabrir"):
        assert cliente.post(_url(edicao), {"acao": acao}).status_code == 403
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None


def test_botoes_conforme_o_estado(conferente):
    edicao, _, projetos, jurados = _edicao()
    _avaliar_todos(jurados, projetos)
    html = conferente.get(_url(edicao)).content.decode()
    assert 'value="concluir"' in html and 'value="reabrir"' not in html
    _concluir(conferente, edicao)
    html = conferente.get(_url(edicao)).content.decode()
    assert 'value="reabrir"' in html and 'value="concluir"' not in html


# --- Reabrir digitação ---------------------------------------------------------------------


def test_reabrir_apaga_registra_e_devolve_a_digitacao(conferente, renan, client):
    edicao, _, projetos, jurados = _edicao()
    _avaliar_todos(jurados, projetos[:2])
    _concluir(conferente, edicao)
    superusuario = User.objects.create_superuser("coord", "c@example.com", "senha-forte-123")
    digitacao = Client()
    digitacao.force_login(superusuario)
    assert str(jurados[0]) not in digitacao.get(ADD).content.decode()

    resposta = _concluir(conferente, edicao, acao="reabrir")
    assert resposta.status_code == 302 and resposta.url == _url(edicao)
    assert "Digitação reaberta" in _mensagens(resposta)[-1]
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None
    log = LogEntry.objects.filter(object_id=str(edicao.pk)).latest("action_time")
    assert log.user == renan and log.change_message == "Digitação reaberta por renan"
    assert log.content_type == ContentType.objects.get_for_model(Edicao)
    pagina = digitacao.get(ADD).content.decode()
    assert str(jurados[0]) in pagina and str(jurados[1]) in pagina
    assert digitacao.get(ADD, {"jurado": jurados[0].pk}).status_code == 200


def test_reabrir_recusa_quando_nao_conferida(conferente):
    edicao, _, projetos, jurados = _edicao()
    _avaliar_todos(jurados, projetos)
    resposta = _concluir(conferente, edicao, acao="reabrir")
    assert resposta.status_code == 302 and _mensagens(resposta)[-1:] == [modulo.NAO_CONFERIDA]
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None
    assert not LogEntry.objects.exists()


# --- Acesso --------------------------------------------------------------------------------


def test_anonimo_e_nao_staff_vao_para_o_login(client):
    edicao, *_ = _edicao()
    for metodo in (client.get, client.post):
        resposta = metodo(_url(edicao))
        assert resposta.status_code == 302 and reverse("admin:login") in resposta.url
    client.force_login(_staff("aluno", "concluir_conferencia", staff=False))
    resposta = client.post(_url(edicao), {"acao": "concluir"})
    assert resposta.status_code == 302 and reverse("admin:login") in resposta.url


def test_staff_sem_permissao_e_digitacao_recebem_403(client):
    edicao, _, projetos, jurados = _edicao()
    _avaliar_todos(jurados, projetos)
    sem = _staff("sem", "imprimir_ficha")
    barbara = User.objects.get(username="barbara")
    barbara.is_staff = True
    barbara.save()
    barbara.groups.add(Group.objects.get(name=GRUPO_DIGITACAO))
    for usuario in (sem, barbara):
        client.force_login(usuario)
        resposta = client.get(_url(edicao))
        assert resposta.status_code == 403 and "no-store" in resposta["Cache-Control"]
        assert client.post(_url(edicao), {"acao": "concluir"}).status_code == 403
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None


def test_inexistente_404_sem_cache(conferente):
    url = reverse("admin:banca_jurado_conferencia", args=[999999])
    for metodo in (conferente.get, conferente.post):
        resposta = metodo(url, {"acao": "concluir"}) if metodo == conferente.post else metodo(url)
        assert resposta.status_code == 404 and "no-store" in resposta["Cache-Control"]


def test_pagina_sem_cache(conferente):
    edicao, *_ = _edicao()
    resposta = conferente.get(_url(edicao))
    assert resposta.status_code == 200 and "no-store" in resposta["Cache-Control"]


def test_rota_vem_antes_das_padrao_e_usa_o_site_do_admin():
    rota = resolve("/admin/banca/jurado/edicao/1/conferencia/")
    assert rota.url_name == "banca_jurado_conferencia"
    assert rota.kwargs["admin_site"] is admin.site._registry[Jurado].admin_site


def test_outros_metodos_405_sem_cache(conferente):
    edicao, *_ = _edicao()
    for metodo in (conferente.put, conferente.delete, conferente.patch):
        resposta = metodo(_url(edicao))
        assert resposta.status_code == 405 and "no-store" in resposta["Cache-Control"]
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None


def test_link_na_tela_do_jurado_so_com_a_permissao(client, renan):
    edicao, _, _, jurados = _edicao()
    url = reverse("admin:banca_jurado_change", args=[jurados[0].pk])
    renan.user_permissions.add(Permission.objects.get(codename="view_jurado"))
    client.force_login(renan)
    assert _url(edicao) in client.get(url).content.decode()
    so_ver = _staff("so_ver")
    so_ver.user_permissions.add(Permission.objects.get(codename="view_jurado"))
    client.force_login(so_ver)
    resposta = client.get(url)
    assert resposta.status_code == 200 and _url(edicao) not in resposta.content.decode()


# --- banca_conferida_em somente leitura no admin de Edicao -------------------------------------


def test_banca_conferida_em_somente_leitura_no_admin_de_edicao():
    edicao = cadastro.edicao()
    superusuario = User.objects.create_superuser("coord", "c@example.com", "senha-forte-123")
    request = RequestFactory().post("/")
    request.user = superusuario
    form_class = admin.ModelAdmin(Edicao, admin.site).get_form(request, edicao, change=True)
    assert "banca_conferida_em" not in form_class.base_fields
    dados = {
        "nome": edicao.nome,
        "data_evento": "29/10/2026",
        "prazo_edicao_0": "28/10/2026",
        "prazo_edicao_1": "23:59",
        "peso_banca": "0.70",
        "peso_publico": "0.30",
        "banca_conferida_em": "30/10/2026 10:00",
    }
    form = form_class(dados, instance=edicao)
    assert form.is_valid(), form.errors
    form.save()
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None


# --- Concorrência real (duas conexões) -------------------------------------------------------


def _em_thread(alvo, *args):
    """Roda `alvo` em outra thread, com conexão própria ao banco."""
    resultado = {}

    def rodar():
        try:
            resultado["valor"] = alvo(*args)
        except Exception as erro:  # noqa: BLE001 — o teste confere
            resultado["erro"] = erro
        finally:
            connections.close_all()

    thread = threading.Thread(target=rodar)
    thread.start()
    return thread, resultado


@pytest.mark.django_db(transaction=True)
def test_concluir_espera_a_ficha_em_gravacao_e_ve_a_avaliacao():
    """Ficha gravada e ainda sem commit (o sinal já travou a Edicao): o concluir
    espera a trava e, ao seguir, vê a avaliação, digitada pelo próprio
    conferente → recusa. Sem a trava antes das verificações, concluiria."""
    edicao, _, projetos, (ana, bia) = _edicao(projetos=2)
    _avaliar_todos([ana], projetos)
    renan = _staff("renan", "concluir_conferencia")
    cliente = Client()
    cliente.force_login(renan)

    with transaction.atomic():
        fabricas.avaliar(bia, projetos[0], [5, 5], renan)
        thread, resultado = _em_thread(lambda: cliente.post(_url(edicao), {"acao": "concluir"}))
        time.sleep(0.5)
        assert thread.is_alive(), "o concluir deveria esperar a trava da Edicao"

    thread.join(timeout=10)
    assert not thread.is_alive() and "erro" not in resultado
    resposta = resultado["valor"]
    assert resposta.status_code == 302 and _mensagens(resposta)[-1:] == [modulo.QUEM_DIGITOU]
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None


# --- Versão das notas (parecer do Renan no #58) ----------------------------------------------


def test_nota_corrigida_depois_de_abrir_a_pagina_impede_concluir(conferente):
    edicao, _, projetos, jurados = _edicao()
    avaliacoes = _avaliar_todos(jurados, projetos)
    vista = _versao_da_pagina(conferente, edicao)  # o conferente abre a página
    nota = avaliacoes[0].notas.first()  # outro usuário corrige uma nota
    nota.valor = 3
    nota.save()
    resposta = _concluir(conferente, edicao, versao=vista)
    assert _mensagens(resposta)[-1:] == [modulo.NOTAS_MUDARAM]
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None
    assert not LogEntry.objects.exists()


def test_avaliacao_nova_ou_apagada_depois_de_abrir_impede_concluir(conferente):
    edicao, _, projetos, jurados = _edicao()
    avaliacoes = _avaliar_todos(jurados[:1], projetos)
    vista = _versao_da_pagina(conferente, edicao)
    fabricas.avaliar(jurados[1], projetos[0], [5, 5])
    assert _mensagens(_concluir(conferente, edicao, versao=vista))[-1:] == [modulo.NOTAS_MUDARAM]
    vista = _versao_da_pagina(conferente, edicao)
    avaliacoes[0].delete()
    assert _mensagens(_concluir(conferente, edicao, versao=vista))[-1:] == [modulo.NOTAS_MUDARAM]
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None


def test_concluir_sem_versao_e_recusado(conferente):
    edicao, _, projetos, jurados = _edicao()
    _avaliar_todos(jurados, projetos)
    resposta = conferente.post(_url(edicao), {"acao": "concluir"})
    assert _mensagens(resposta)[-1:] == [modulo.NOTAS_MUDARAM]
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None


def test_conferir_de_novo_depois_da_correcao_conclui(conferente):
    edicao, _, projetos, jurados = _edicao()
    avaliacoes = _avaliar_todos(jurados, projetos)
    vista = _versao_da_pagina(conferente, edicao)
    nota = avaliacoes[0].notas.first()
    nota.valor = 3
    nota.save()
    _concluir(conferente, edicao, versao=vista)
    resposta = _concluir(conferente, edicao)  # reabre a página (versão nova) e conclui
    assert _mensagens(resposta)[-1:] == ["Conferência concluída."]
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is not None


def test_versao_nao_muda_com_outra_edicao():
    edicao, _, projetos, jurados = _edicao()
    _avaliar_todos(jurados, projetos)
    antes = modulo.versao_da_banca(edicao.pk)
    outra, _, outros, js = _edicao(nome="Outra", sigla="X")
    _avaliar_todos(js, outros)
    assert modulo.versao_da_banca(edicao.pk) == antes
