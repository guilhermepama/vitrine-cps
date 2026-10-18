"""Avaliadores convidados (ADR-013; specs/06-avaliacao-banca.md, "Avaliadores convidados")."""

import re
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from banca.sinais import GRUPO_DIGITACAO
from banca.models import Avaliacao, Criterio, Jurado, Nota, Tipo
from banca.servicos import nota_banca_por_projeto
from banca.tests import fabricas
from cadastro.models import Projeto
from cadastro.tests import fabricas as cadastro
from votacao.servicos import abrir_votacao, encerrar_votacao

pytestmark = pytest.mark.django_db
D = Decimal


def _cenario(projetos=2, sigla="DSM"):
    """Edição com 2 critérios de banca e 4 de convidado, uma turma, votação aberta."""
    edicao = cadastro.edicao(peso_banca=D("0.50"), peso_convidados=D("0.20"), peso_publico=D("0.30"))
    turma = cadastro.turma(edicao, cadastro.curso(sigla))
    lista = [cadastro.projeto(turma, titulo=f"Projeto {i}", status=Projeto.Status.PUBLICADO) for i in range(projetos)]
    for i in range(2):
        Criterio.objects.create(edicao=edicao, nome=f"Técnico {i + 1}", ordem=i + 1)
    fabricas.criterios_de_convidado(edicao)
    assert abrir_votacao(edicao.pk) is None
    edicao.refresh_from_db()
    return edicao, turma, lista


# --- Modelo ----------------------------------------------------------------------


def test_jurado_e_criterio_nascem_como_banca():
    edicao = cadastro.edicao()
    assert Jurado.objects.create(edicao=edicao, nome="Ana").tipo == Tipo.BANCA
    assert Criterio.objects.create(edicao=edicao, nome="Técnico", ordem=1).tipo == Tipo.BANCA


def test_mesmo_nome_e_ordem_em_tipos_diferentes_e_barrado_dentro_do_tipo():
    edicao = cadastro.edicao()
    Criterio.objects.create(edicao=edicao, nome="Inovação", ordem=1)
    Criterio.objects.create(edicao=edicao, tipo=Tipo.CONVIDADO, nome="Inovação", ordem=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        Criterio.objects.create(edicao=edicao, tipo=Tipo.CONVIDADO, nome="Inovação", ordem=2)


def test_nota_de_criterio_de_outro_tipo_e_recusada():
    edicao, turma, projetos = _cenario()
    banca = fabricas.jurado(edicao, turma)
    avaliacao = Avaliacao.objects.create(jurado=banca, projeto=projetos[0], digitado_por=fabricas.digitador())
    de_convidado = Criterio.objects.filter(edicao=edicao, tipo=Tipo.CONVIDADO).first()
    with pytest.raises(ValidationError, match="outro tipo"):
        Nota(avaliacao=avaliacao, criterio=de_convidado, valor=D("7")).full_clean()


def test_convidado_sem_criterios_de_convidado_nao_avalia():
    edicao, turma, projetos = fabricas.cenario()  # só critérios de banca
    convidado = fabricas.jurado(edicao, turma, "Carlos", Tipo.CONVIDADO)
    avaliacao = Avaliacao(jurado=convidado, projeto=projetos[0], digitado_por=fabricas.digitador())
    with pytest.raises(ValidationError, match="não tem critérios de avaliador convidado cadastrados"):
        avaliacao.full_clean()


def test_jurado_com_avaliacao_nao_muda_de_tipo():
    edicao, turma, projetos = _cenario()
    banca = fabricas.jurado(edicao, turma)
    fabricas.avaliar(banca, projetos[0], [7, 8])
    banca.tipo = Tipo.CONVIDADO
    with pytest.raises(ValidationError, match="não muda de tipo"):
        banca.save()
    assert Jurado.objects.get(pk=banca.pk).tipo == Tipo.BANCA


def test_jurado_sem_avaliacao_pode_mudar_de_tipo():
    edicao, turma, _ = _cenario()
    jurado = fabricas.jurado(edicao, turma)
    jurado.tipo = Tipo.CONVIDADO
    jurado.save()
    assert Jurado.objects.get(pk=jurado.pk).tipo == Tipo.CONVIDADO


# --- Corrida entre trocar o tipo e digitar a primeira ficha (revisão do Renan no #82)


def test_ficha_validada_com_tipo_antigo_e_recusada():
    """O tipo mudou entre abrir a ficha e gravar: clean e save recusam."""
    edicao, turma, projetos = _cenario()
    jurado = fabricas.jurado(edicao, turma)  # objeto com o tipo de quando a ficha abriu
    Jurado.objects.filter(pk=jurado.pk).update(tipo=Tipo.CONVIDADO)
    avaliacao = Avaliacao(jurado=jurado, projeto=projetos[0], digitado_por=fabricas.digitador())
    with pytest.raises(ValidationError, match="tipo deste jurado mudou"):
        avaliacao.full_clean()
    with pytest.raises(ValidationError, match="tipo deste jurado mudou"):
        avaliacao.save()
    assert not Avaliacao.objects.exists()


def test_digitacao_volta_com_erro_se_o_tipo_muda_no_meio_do_post(digitacao, monkeypatch):
    edicao, turma, projetos = _cenario()
    ana = fabricas.jurado(edicao, turma)
    original = Avaliacao.clean

    def clean(self):  # outra pessoa troca o tipo depois que o formulário leu o jurado
        Jurado.objects.filter(pk=ana.pk).update(tipo=Tipo.CONVIDADO)
        original(self)

    monkeypatch.setattr(Avaliacao, "clean", clean)
    da_banca = list(Criterio.objects.filter(edicao=edicao, tipo=Tipo.BANCA).order_by("ordem"))
    resposta = digitacao.post(f"{ADD}?jurado={ana.pk}", _post(projetos[0], da_banca, ["7,0", "8,0"]))
    assert resposta.status_code == 200
    assert "tipo deste jurado mudou" in resposta.content.decode()
    assert not Avaliacao.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_trocar_tipo_espera_a_primeira_ficha_e_e_recusado():
    """A primeira ficha trava a linha do jurado: a troca de tipo espera a
    gravação e então encontra a avaliação."""
    import threading
    import time

    from django.db import connection

    edicao, turma, projetos = _cenario()
    ana = fabricas.jurado(edicao, turma)
    usuario = fabricas.digitador()
    travou, erros = threading.Event(), []

    def digitar_primeira_ficha():
        try:
            with transaction.atomic():
                avaliacao = Avaliacao(jurado=Jurado.objects.get(pk=ana.pk), projeto=projetos[0], digitado_por=usuario)
                avaliacao.full_clean()  # trava a linha do jurado
                travou.set()
                time.sleep(0.5)  # a troca de tipo tenta agora e precisa esperar
                avaliacao.save()
                for criterio, valor in zip(Criterio.objects.filter(edicao=edicao, tipo=Tipo.BANCA).order_by("ordem"), [7, 8]):
                    Nota.objects.create(avaliacao=avaliacao, criterio=criterio, valor=D(valor))
        except Exception as erro:  # pragma: no cover - aparece na asserção
            erros.append(erro)
        finally:
            connection.close()

    t = threading.Thread(target=digitar_primeira_ficha)
    t.start()
    assert travou.wait(5)
    outra_aba = Jurado.objects.get(pk=ana.pk)
    outra_aba.tipo = Tipo.CONVIDADO
    with pytest.raises(ValidationError, match="não muda de tipo"):
        outra_aba.save()
    t.join(5)
    assert not erros
    assert Jurado.objects.get(pk=ana.pk).tipo == Tipo.BANCA
    assert Nota.objects.filter(avaliacao__jurado=ana, criterio__tipo=Tipo.BANCA).count() == 2


# --- Nota por tipo -----------------------------------------------------------------


def test_nota_por_projeto_separa_banca_e_convidados():
    edicao, turma, projetos = _cenario()
    ana, bia = fabricas.jurado(edicao, turma, "Ana"), fabricas.jurado(edicao, turma, "Bia")
    carlos = fabricas.jurado(edicao, turma, "Carlos", Tipo.CONVIDADO)
    fabricas.avaliar(ana, projetos[0], [6, 8])  # média 7
    fabricas.avaliar(bia, projetos[0], [8, 10])  # média 9
    fabricas.avaliar(carlos, projetos[0], [4, 5, 6, 5])  # média 5
    assert nota_banca_por_projeto(edicao) == {projetos[0].pk: D("8")}
    assert nota_banca_por_projeto(edicao, Tipo.BANCA) == {projetos[0].pk: D("8")}
    assert nota_banca_por_projeto(edicao, Tipo.CONVIDADO) == {projetos[0].pk: D("5")}


# --- Digitação ---------------------------------------------------------------------


@pytest.fixture
def digitacao(client):
    barbara = User.objects.create_user("barbara", "b@example.com", "senha-forte-123", is_staff=True)
    barbara.groups.add(Group.objects.get(name=GRUPO_DIGITACAO))
    client.force_login(barbara)
    return client


ADD = reverse("admin:banca_avaliacao_add")


def _post(projeto, criterios, valores):
    dados = {
        "projeto": projeto.pk,
        "notas-TOTAL_FORMS": len(criterios),
        "notas-INITIAL_FORMS": 0,
        "notas-MIN_NUM_FORMS": 0,
        "notas-MAX_NUM_FORMS": 1000,
    }
    for i, (criterio, valor) in enumerate(zip(criterios, valores)):
        dados[f"notas-{i}-criterio"] = criterio.pk
        dados[f"notas-{i}-valor"] = valor
    return dados


def test_digitacao_do_convidado_tem_uma_nota_por_criterio_de_convidado(digitacao):
    edicao, turma, projetos = _cenario()
    carlos = fabricas.jurado(edicao, turma, "Carlos", Tipo.CONVIDADO)
    html = digitacao.get(f"{ADD}?jurado={carlos.pk}").content.decode()
    assert "Viabilidade econômica" in html and "Técnico 1" not in html
    criterios = list(Criterio.objects.filter(edicao=edicao, tipo=Tipo.CONVIDADO).order_by("ordem"))
    resposta = digitacao.post(f"{ADD}?jurado={carlos.pk}", _post(projetos[0], criterios, ["7,0", "8,0", "6,5", "9,0"]))
    assert resposta.status_code == 302
    assert Nota.objects.filter(avaliacao__jurado=carlos).count() == 4


def test_digitacao_do_convidado_com_criterios_da_banca_e_recusada(digitacao):
    edicao, turma, projetos = _cenario()
    carlos = fabricas.jurado(edicao, turma, "Carlos", Tipo.CONVIDADO)
    da_banca = list(Criterio.objects.filter(edicao=edicao, tipo=Tipo.BANCA).order_by("ordem"))
    resposta = digitacao.post(f"{ADD}?jurado={carlos.pk}", _post(projetos[0], da_banca, ["7,0", "8,0"]))
    assert resposta.status_code == 200 and not Avaliacao.objects.exists()


# --- Ficha -------------------------------------------------------------------------


@pytest.fixture
def impressor(client):
    usuario = User.objects.create_user("coord", "c@example.com", "senha-forte-123", is_staff=True)
    usuario.user_permissions.add(Permission.objects.get(content_type__app_label="banca", codename="imprimir_ficha"))
    client.force_login(usuario)
    return client


def test_ficha_do_convidado_traz_so_os_criterios_dele(impressor):
    edicao, turma, projetos = _cenario()
    carlos = fabricas.jurado(edicao, turma, "Carlos", Tipo.CONVIDADO)
    html = impressor.get(reverse("admin:banca_jurado_ficha", args=[carlos.pk])).content.decode()
    assert "Ficha do avaliador convidado — " in html and "<strong>Avaliador convidado:</strong> Carlos" in html
    assert "Viabilidade econômica" in html and "Técnico 1" not in html
    linha = re.search(rf'<tr><td class="numero">#{projetos[0].pk}</td>.*?</tr>', html).group(0)
    assert linha.count('<td class="nota"></td>') == 4


def test_fichas_da_edicao_poem_a_banca_antes_dos_convidados(impressor):
    edicao, turma, _ = _cenario()
    fabricas.jurado(edicao, turma, "Zé", Tipo.BANCA)
    fabricas.jurado(edicao, turma, "Alice", Tipo.CONVIDADO)
    html = impressor.get(reverse("admin:banca_jurado_fichas_edicao", args=[edicao.pk])).content.decode()
    assert html.index("<strong>Jurado:</strong> Zé") < html.index("<strong>Avaliador convidado:</strong> Alice")


# --- Conferência -----------------------------------------------------------------------


@pytest.fixture
def conferente(client):
    usuario = User.objects.create_user("renan", "r@example.com", "senha-forte-123", is_staff=True)
    usuario.user_permissions.add(Permission.objects.get(content_type__app_label="banca", codename="concluir_conferencia"))
    client.force_login(usuario)
    return client


def _conferencia(client, edicao):
    return client.get(reverse("admin:banca_jurado_conferencia", args=[edicao.pk])).content.decode()


def test_conferencia_mostra_projeto_sem_avaliacao_de_convidado(conferente):
    edicao, turma, projetos = _cenario()
    ana = fabricas.jurado(edicao, turma, "Ana")
    carlos = fabricas.jurado(edicao, turma, "Carlos", Tipo.CONVIDADO)
    for p in projetos:
        fabricas.avaliar(ana, p, [7, 8])
    fabricas.avaliar(carlos, projetos[0], [7, 7, 7, 7])
    assert encerrar_votacao(edicao.pk) is None
    html = _conferencia(conferente, edicao)
    sem = re.search(r'<ul class="sem-avaliacao convidado">(.*?)</ul>', html).group(1)
    assert sem == f"<li>#{projetos[1].pk} — {projetos[1].titulo}</li>"
    assert '<ul class="sem-avaliacao">' not in html  # a banca cobriu todos
    assert "<h3>Avaliadores convidados</h3>" in html and 'id="amostra-convidado"' in html
    assert "ou, quando os convidados têm peso, sem avaliação de convidado fica com o resultado pendente" in html
    assert "Sem nenhuma avaliação (banca pendente)" not in html


def test_conferencia_avisa_jurado_que_cobre_so_parte_do_curso(conferente):
    edicao, turma, projetos = _cenario()
    outra = cadastro.turma(edicao, turma.curso, numero_periodo=1)
    cadastro.projeto(outra, titulo="Do 1º", status=Projeto.Status.PUBLICADO)
    fabricas.jurado(edicao, turma, "Ana")  # só a turma do 3º
    html = _conferencia(conferente, edicao)
    aviso = re.search(r'<ul class="cobertura-parcial">(.*?)</ul>', html).group(1)
    assert "Ana (banca) avalia DSM — 3º semestre, mas não DSM — 1º semestre." in aviso


def test_edicao_so_com_banca_nao_mostra_blocos_de_convidado(conferente):
    edicao, turma, projetos = fabricas.cenario()
    fabricas.jurado(edicao, turma, "Ana")
    html = _conferencia(conferente, edicao)
    assert "convidado" not in html.lower().replace("avaliador convidado", "")
    # Página exatamente como antes da ADR-013: o texto da pendência não muda.
    assert "<p>Sem nenhuma avaliação (banca pendente):</p>" in html
    assert "A turma fica com banca pendente no resultado." in html
