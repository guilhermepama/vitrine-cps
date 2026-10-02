"""Abrir e encerrar a votação — fatia F2 (specs/03-credenciamento-votacao.md).

Critérios de aceite fechados aqui (citados em cada teste):
- "Abrir com outra edição em votação → recusado, nenhuma Edicao alterada"
- "Teste de concorrência: duas aberturas simultâneas de edições diferentes →
  no máximo uma edição com votacao_aberta_em preenchido e
  votacao_encerrada_em vazio"
- "Abrir edição já encerrada → 'não pode ser reaberta', campos inalterados"
- "Encerrar edição não aberta ou já encerrada → recusado, campos inalterados"
- "Abrir e encerrar gravam pela instância com save(); nenhum
  QuerySet.update()/bulk_update em campo da Edicao no app votacao" (N2)
- Isolamento: "Encerrar o ensaio e abrir o evento não altera nem apaga
  tokens, votos ou visitantes do ensaio"
- Estação, com a trava da Edicao (corrida A8 do plano): troca de edição
  concorrente com uma emissão não deixa token em outra edição.
"""

import ast
import threading
import time
from datetime import date
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.db import connections, transaction
from django.forms.models import model_to_dict

from cadastro.models import Edicao
from cadastro.tests import fabricas as cadastro
from votacao import servicos
from votacao.models import Estacao, Token, Visitante, Voto
from votacao.servicos import abrir_votacao, edicao_em_votacao, encerrar_votacao
from votacao.tests import fabricas

pytestmark = pytest.mark.django_db


def _ensaio():
    return cadastro.edicao(nome="Ensaio 2026/2", data_evento=date(2026, 10, 22))


def _foto_edicoes():
    return {e.pk: model_to_dict(e) | {"aberta": e.votacao_aberta_em, "encerrada": e.votacao_encerrada_em}
            for e in Edicao.objects.all()}


def _em_votacao():
    return list(Edicao.objects.filter(votacao_aberta_em__isnull=False, votacao_encerrada_em__isnull=True))


# --- Abrir --------------------------------------------------------------------


def test_abrir_grava_abertura_e_a_edicao_fica_em_votacao():
    evento = cadastro.edicao()
    assert abrir_votacao(evento.pk) is None
    evento.refresh_from_db()
    assert evento.votacao_aberta_em is not None
    assert evento.votacao_encerrada_em is None
    assert edicao_em_votacao() == evento


def test_abrir_com_outra_edicao_em_votacao_e_recusado_sem_alterar_nada():
    """Critério: "Abrir com outra edição em votação → recusado, nenhuma Edicao alterada"."""
    ensaio, evento = _ensaio(), cadastro.edicao()
    abrir_votacao(ensaio.pk)
    antes = _foto_edicoes()

    recusa = abrir_votacao(evento.pk)

    assert recusa == "Já existe uma votação aberta (Ensaio 2026/2). Encerre-a antes de abrir outra."
    assert _foto_edicoes() == antes


def test_abrir_edicao_ja_aberta_e_recusado():
    evento = cadastro.edicao()
    abrir_votacao(evento.pk)
    antes = _foto_edicoes()
    assert abrir_votacao(evento.pk) == "A votação desta edição já foi aberta e não pode ser reaberta."
    assert _foto_edicoes() == antes


def test_abrir_edicao_encerrada_nao_reabre():
    """Critério: "Abrir edição já encerrada → 'não pode ser reaberta', campos inalterados"."""
    evento = cadastro.edicao()
    abrir_votacao(evento.pk)
    encerrar_votacao(evento.pk)
    antes = _foto_edicoes()

    assert abrir_votacao(evento.pk) == "A votação desta edição já foi aberta e não pode ser reaberta."
    assert _foto_edicoes() == antes
    assert edicao_em_votacao() is None


def test_abrir_outra_depois_de_encerrar_a_anterior():
    ensaio, evento = _ensaio(), cadastro.edicao()
    abrir_votacao(ensaio.pk)
    encerrar_votacao(ensaio.pk)
    assert abrir_votacao(evento.pk) is None
    assert edicao_em_votacao() == evento


def test_abrir_edicao_inexistente_levanta_does_not_exist():
    with pytest.raises(Edicao.DoesNotExist):
        abrir_votacao(999_999)


# --- Encerrar -----------------------------------------------------------------


def test_encerrar_grava_encerramento_depois_da_abertura():
    evento = cadastro.edicao()
    abrir_votacao(evento.pk)
    assert encerrar_votacao(evento.pk) is None
    evento.refresh_from_db()
    assert evento.votacao_encerrada_em >= evento.votacao_aberta_em
    assert edicao_em_votacao() is None


def test_encerrar_edicao_nao_aberta_e_recusado():
    """Critério: "Encerrar edição não aberta ou já encerrada → recusado, campos inalterados" (não aberta)."""
    evento = cadastro.edicao()
    antes = _foto_edicoes()
    assert encerrar_votacao(evento.pk) == "A votação desta edição ainda não foi aberta."
    assert _foto_edicoes() == antes


def test_encerrar_edicao_ja_encerrada_e_recusado():
    """Critério: "Encerrar edição não aberta ou já encerrada → recusado, campos inalterados" (já encerrada)."""
    evento = cadastro.edicao()
    abrir_votacao(evento.pk)
    encerrar_votacao(evento.pk)
    antes = _foto_edicoes()
    assert encerrar_votacao(evento.pk) == "A votação desta edição já foi encerrada."
    assert _foto_edicoes() == antes


# --- edicao_em_votacao --------------------------------------------------------


def test_edicao_em_votacao_sem_nenhuma_aberta_e_none():
    cadastro.edicao()
    assert edicao_em_votacao() is None


def test_edicao_em_votacao_travada_exige_transacao():
    evento = cadastro.edicao()
    abrir_votacao(evento.pk)
    with transaction.atomic():
        assert edicao_em_votacao(travar=True) == evento


# --- Só via save() (N2) -------------------------------------------------------


def test_abrir_e_encerrar_passam_pelo_save_do_model(monkeypatch):
    """Critério N2: gravam pela instância com save() — o save() do cadastro aplica as travas."""
    chamadas = []
    original = Edicao.save

    def espiao(self, *args, **kwargs):
        chamadas.append(kwargs.get("update_fields"))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Edicao, "save", espiao)
    evento = cadastro.edicao()
    abrir_votacao(evento.pk)
    encerrar_votacao(evento.pk)
    assert chamadas[-2:] == [["votacao_aberta_em"], ["votacao_encerrada_em"]]


def test_codigo_do_app_votacao_nao_usa_update_nem_bulk_update():
    """Critério N2 (revisão de código): nenhum QuerySet.update()/bulk_update no app votacao."""
    app = Path(servicos.__file__).parent
    fontes = [p for p in app.rglob("*.py") if "tests" not in p.parts and "migrations" not in p.parts]
    assert fontes
    achados = [
        f"{p.name}:{no.lineno}"
        for p in fontes
        for no in ast.walk(ast.parse(p.read_text()))
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
        and no.func.attr in {"update", "bulk_update"}
    ]
    assert achados == []


# --- Isolamento por edição ----------------------------------------------------


def test_encerrar_ensaio_e_abrir_evento_nao_mexe_nos_dados_do_ensaio():
    """Critério: "Encerrar o ensaio e abrir o evento não altera nem apaga tokens, votos ou visitantes do ensaio"."""
    ensaio, evento = _ensaio(), cadastro.edicao()
    abrir_votacao(ensaio.pk)
    voto = fabricas.voto(fabricas.token(fabricas.estacao(ensaio)))
    fabricas.visitante(ensaio)

    def foto():
        return (
            list(Token.objects.values().order_by("id")),
            list(Voto.objects.values().order_by("id")),
            list(Visitante.objects.values().order_by("id")),
            list(Estacao.objects.values().order_by("id")),
        )

    antes = foto()
    assert encerrar_votacao(ensaio.pk) is None
    assert abrir_votacao(evento.pk) is None

    assert foto() == antes
    assert voto.token.estacao.edicao_id == ensaio.pk
    assert edicao_em_votacao() == evento


# --- Concorrência real (duas conexões) ---------------------------------------


def _em_thread(alvo, *args):
    """Roda `alvo` em outra thread, com conexão própria ao banco."""
    resultado = {}

    def rodar():
        try:
            resultado["valor"] = alvo(*args)
        except Exception as erro:  # noqa: BLE001 — o teste confere o tipo
            resultado["erro"] = erro
        finally:
            connections.close_all()

    thread = threading.Thread(target=rodar)
    thread.start()
    return thread, resultado


@pytest.mark.django_db(transaction=True)
def test_duas_aberturas_simultaneas_deixam_no_maximo_uma_edicao_em_votacao():
    """Critério: "duas aberturas simultâneas de edições diferentes → no máximo uma
    edição com votacao_aberta_em preenchido e votacao_encerrada_em vazio" (G4)."""
    ensaio, evento = _ensaio(), cadastro.edicao()
    largada = threading.Barrier(2)

    def abrir(edicao_id):
        largada.wait()
        return abrir_votacao(edicao_id)

    corridas = [_em_thread(abrir, ensaio.pk), _em_thread(abrir, evento.pk)]
    for thread, _ in corridas:
        thread.join(timeout=10)
        assert not thread.is_alive()

    resultados = [r for _, r in corridas]
    assert all("erro" not in r for r in resultados)
    respostas = sorted([r["valor"] for r in resultados], key=lambda v: v is not None)
    assert respostas[0] is None
    assert respostas[1].startswith("Já existe uma votação aberta")
    assert len(_em_votacao()) == 1


@pytest.mark.django_db(transaction=True)
def test_abertura_espera_a_trava_de_outra_abertura_e_ve_o_resultado():
    """Versão determinística da corrida: com a primeira abertura ainda sem commit,
    a segunda fica bloqueada na trava e, ao seguir, vê a outra em votação."""
    ensaio, evento = _ensaio(), cadastro.edicao()

    with transaction.atomic():
        travadas = list(Edicao.objects.select_for_update().order_by("pk"))
        primeira = next(e for e in travadas if e.pk == ensaio.pk)
        primeira.votacao_aberta_em = primeira.criado_em
        primeira.save(update_fields=["votacao_aberta_em"])

        thread, resultado = _em_thread(abrir_votacao, evento.pk)
        time.sleep(0.5)
        assert thread.is_alive(), "a segunda abertura deveria esperar a trava"

    thread.join(timeout=10)
    assert resultado == {"valor": "Já existe uma votação aberta (Ensaio 2026/2). Encerre-a antes de abrir outra."}
    assert _em_votacao() == [ensaio]


@pytest.mark.django_db(transaction=True)
def test_troca_de_edicao_da_estacao_espera_emissao_em_andamento_e_e_recusada():
    """Corrida A8: a emissão trava a edição em votação antes de ler a estação e
    gravar o token; a troca de edição trava a mesma linha e, ao seguir, vê o token."""
    evento, outra = cadastro.edicao(), _ensaio()
    abrir_votacao(evento.pk)
    estacao = fabricas.estacao(evento)

    def trocar_edicao():
        e = Estacao.objects.get(pk=estacao.pk)
        e.edicao = outra
        e.save()

    with transaction.atomic():
        # Emissão (F4) em andamento: trava a edição em votação e grava o token.
        assert edicao_em_votacao(travar=True) == evento
        Token.objects.create(estacao=Estacao.objects.get(pk=estacao.pk, edicao=evento, ativa=True))

        thread, resultado = _em_thread(trocar_edicao)
        time.sleep(0.5)
        assert thread.is_alive(), "a troca de edição deveria esperar a trava da edição"

    thread.join(timeout=10)
    assert isinstance(resultado.get("erro"), ValidationError)
    estacao.refresh_from_db()
    assert estacao.edicao_id == evento.pk
    assert Token.objects.filter(estacao__edicao=evento).count() == 1


@pytest.mark.django_db(transaction=True)
def test_emissao_que_espera_troca_de_edicao_ve_a_estacao_em_outra_edicao():
    """Corrida A8, outra ordem: a troca obteve a trava primeiro; a emissão espera
    e, ao ler a estação depois da trava, já a vê em outra edição (não emite)."""
    evento, outra = cadastro.edicao(), _ensaio()
    abrir_votacao(evento.pk)
    estacao = fabricas.estacao(evento)

    def emitir():
        with transaction.atomic():
            em_votacao = edicao_em_votacao(travar=True)
            return Estacao.objects.filter(pk=estacao.pk, edicao=em_votacao, ativa=True).exists()

    with transaction.atomic():
        e = Estacao.objects.get(pk=estacao.pk)
        e.edicao = outra
        e.save()

        thread, resultado = _em_thread(emitir)
        time.sleep(0.5)
        assert thread.is_alive(), "a emissão deveria esperar a trava da edição"

    thread.join(timeout=10)
    assert resultado == {"valor": False}
    assert Token.objects.count() == 0
