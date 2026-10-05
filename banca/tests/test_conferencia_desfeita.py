"""Corrigir nota depois da conferência apaga `banca_conferida_em` (spec 06)."""

from decimal import Decimal

import pytest
from django.utils import timezone

from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext

from banca import servicos, sinais
from banca.models import Avaliacao, Criterio, Nota
from banca.tests import fabricas

pytestmark = pytest.mark.django_db


@pytest.fixture
def conferida():
    edicao, turma, projetos = fabricas.cenario()
    jurado = fabricas.jurado(edicao, turma)
    avaliacao = fabricas.avaliar(jurado, projetos[0], [7, 8])
    fabricas.avaliar(jurado, projetos[1], [5, 6])
    edicao.banca_conferida_em = timezone.now()
    edicao.save(update_fields=["banca_conferida_em"])
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
    edicao.save(update_fields=["banca_conferida_em"])
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


def _conferir(edicao):
    edicao.banca_conferida_em = timezone.now()
    edicao.save(update_fields=["banca_conferida_em"])


def test_criar_avaliacao_sem_notas_desfaz():
    """O post_save da própria Avaliacao, sem depender das notas."""
    edicao, turma, projetos = fabricas.cenario()
    jurado = fabricas.jurado(edicao, turma)
    _conferir(edicao)
    Avaliacao.objects.create(jurado=jurado, projeto=projetos[0], digitado_por=fabricas.digitador())
    assert not _conferida(edicao)


def test_apagar_avaliacao_sem_notas_desfaz():
    edicao, turma, projetos = fabricas.cenario()
    avaliacao = Avaliacao.objects.create(
        jurado=fabricas.jurado(edicao, turma), projeto=projetos[0], digitado_por=fabricas.digitador()
    )
    _conferir(edicao)
    avaliacao.delete()
    assert not _conferida(edicao)


def test_trocar_o_criterio_da_nota_desfaz(conferida):
    edicao, _, _, avaliacao = conferida
    nota = avaliacao.notas.get(criterio__ordem=1)
    outra = avaliacao.notas.get(criterio__ordem=2)
    outra.delete()
    _conferir(edicao)
    nota.criterio = Criterio.objects.get(edicao=edicao, ordem=2)
    nota.save()
    assert not _conferida(edicao)


def test_mover_avaliacao_de_edicao_desfaz_as_duas(conferida):
    edicao, jurado, projetos, avaliacao = conferida
    outra, turma_o, projetos_o = fabricas.cenario(nome="Ensaio 2026/2", sigla="GTUR")
    _conferir(outra)
    avaliacao.jurado = fabricas.jurado(outra, turma_o)
    avaliacao.projeto = projetos_o[0]
    avaliacao.save()
    assert not _conferida(edicao) and not _conferida(outra)


def test_instancia_velha_gravando_por_cima_desfaz(conferida):
    edicao, _, _, avaliacao = conferida
    velha = Nota.objects.get(pk=avaliacao.notas.first().pk)
    nova = Nota.objects.get(pk=velha.pk)
    nova.valor = Decimal("1.0")
    nova.save()
    _conferir(edicao)
    velha.save()  # volta ao valor antigo: é mudança no banco
    assert not _conferida(edicao)


def test_falha_ao_desfazer_desfaz_a_gravacao_da_nota(conferida):
    """Mesma transação: se o desfazer falha, a nota não fica gravada."""
    _, _, _, avaliacao = conferida
    nota = avaliacao.notas.first()
    antes = nota.valor
    nota.valor = Decimal("9.9")
    with mock.patch.object(sinais, "desfazer_conferencia", side_effect=RuntimeError):
        with pytest.raises(RuntimeError):
            nota.save()
    nota.refresh_from_db()
    assert nota.valor == antes


def test_desfazer_trava_a_edicao(conferida):
    edicao = conferida[0]
    with CaptureQueriesContext(connection) as consultas:
        from django.db import transaction

        with transaction.atomic():
            assert servicos.desfazer_conferencia(edicao.pk) is True
    # A leitura da Edicao (antes do save) já é travada — não só a do Edicao.save().
    primeira = next(q["sql"] for q in consultas.captured_queries if q["sql"].startswith("SELECT"))
    assert "FOR UPDATE" in primeira


def test_campos_adiados_nao_quebram(conferida):
    assert len(list(Avaliacao.objects.only("id"))) == 2
    assert len(list(Nota.objects.defer("valor"))) == 4
