"""Corrigir nota depois da conferência apaga `banca_conferida_em` (spec 06)."""

from decimal import Decimal

import pytest
from django.utils import timezone

from banca.models import Avaliacao, Nota
from banca.tests import fabricas

pytestmark = pytest.mark.django_db


@pytest.fixture
def conferida():
    edicao, turma, projetos = fabricas.cenario()
    jurado = fabricas.jurado(edicao, turma)
    avaliacao = fabricas.avaliar(jurado, projetos[0], [7, 8])
    fabricas.avaliar(jurado, projetos[1], [5, 6])
    edicao.banca_conferida_em = timezone.now()
    edicao.save()
    return edicao, jurado, projetos, avaliacao


def _conferida(edicao):
    edicao.refresh_from_db()
    return edicao.banca_conferida_em is not None


def test_alterar_nota_desfaz(conferida):
    edicao, _, _, avaliacao = conferida
    nota = avaliacao.notas.first()
    nota.valor = Decimal("9.5")
    nota.save()
    assert not _conferida(edicao)


def test_salvar_sem_mudanca_nao_desfaz(conferida):
    edicao, _, _, avaliacao = conferida
    Nota.objects.get(pk=avaliacao.notas.first().pk).save()
    avaliacao = Avaliacao.objects.get(pk=avaliacao.pk)
    avaliacao.alterado_em = timezone.now()  # registro de quem mexeu não conta como mudança de nota
    avaliacao.save()
    assert _conferida(edicao)


def test_criar_avaliacao_desfaz():
    edicao, turma, projetos = fabricas.cenario()
    jurado = fabricas.jurado(edicao, turma)
    fabricas.avaliar(jurado, projetos[0], [7, 8])
    edicao.banca_conferida_em = timezone.now()
    edicao.save()
    fabricas.avaliar(jurado, projetos[1], [5, 6])
    assert not _conferida(edicao)


def test_apagar_avaliacao_desfaz(conferida):
    edicao, _, _, avaliacao = conferida
    avaliacao.delete()  # as notas vão em cascata
    assert not _conferida(edicao)


def test_apagar_em_lote_desfaz(conferida):
    """Como a ação "apagar selecionados" do admin: queryset.delete()."""
    edicao = conferida[0]
    Avaliacao.objects.filter(jurado__edicao=edicao).delete()
    assert not _conferida(edicao)
    assert not Nota.objects.exists()


def test_apagar_so_uma_nota_desfaz(conferida):
    edicao, _, _, avaliacao = conferida
    avaliacao.notas.first().delete()
    assert not _conferida(edicao)


def test_sem_conferencia_nada_muda():
    edicao, turma, projetos = fabricas.cenario()
    fabricas.avaliar(fabricas.jurado(edicao, turma), projetos[0], [7, 8])
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None
