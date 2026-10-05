"""Critérios de aceite "Nota de banca" da spec 06."""

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from banca.models import Avaliacao, Criterio
from banca.servicos import nota_banca_por_projeto
from banca.tests import fabricas
from cadastro.models import Projeto
from cadastro.tests import fabricas as cadastro

pytestmark = pytest.mark.django_db


def test_media_dos_criterios_e_depois_entre_jurados():
    edicao, turma, projetos = fabricas.cenario()
    fabricas.avaliar(fabricas.jurado(edicao, turma, "A"), projetos[0], [8, 6])
    fabricas.avaliar(fabricas.jurado(edicao, turma, "B"), projetos[0], [10, 10])
    notas = nota_banca_por_projeto(edicao)
    assert notas[projetos[0].pk] == Decimal("8.5")  # média de 7 e 10
    assert isinstance(notas[projetos[0].pk], Decimal)


def test_sem_arredondamento():
    edicao, turma, projetos = fabricas.cenario(criterios=3)
    fabricas.avaliar(fabricas.jurado(edicao, turma), projetos[0], [7, 7, 8])
    nota = nota_banca_por_projeto(edicao)[projetos[0].pk]
    assert nota > Decimal("7.3333") and nota < Decimal("7.3334")


def test_projeto_sem_avaliacao_ou_nao_publicado_nao_aparece():
    edicao = cadastro.edicao()
    turma = cadastro.turma(edicao)
    avaliado = cadastro.projeto(turma, titulo="Avaliado", status=Projeto.Status.PUBLICADO)
    sem_nota = cadastro.projeto(turma, titulo="Sem nota", status=Projeto.Status.PUBLICADO)
    rascunho = cadastro.projeto(turma, titulo="Rascunho")
    Criterio.objects.create(edicao=edicao, nome="C1", ordem=1)
    from votacao.servicos import abrir_votacao

    assert abrir_votacao(edicao.pk) is None
    jurado = fabricas.jurado(edicao, turma)
    fabricas.avaliar(jurado, avaliado, [6])
    # Gravada sem passar pela validação (que recusaria): a função filtra de novo.
    fabricas.avaliar(jurado, rascunho, [9])
    assert nota_banca_por_projeto(edicao) == {avaliado.pk: Decimal("6")}
    assert sem_nota.pk not in nota_banca_por_projeto(edicao)


def test_isolamento_por_edicao():
    edicao, turma, projetos = fabricas.cenario()
    fabricas.avaliar(fabricas.jurado(edicao, turma), projetos[0], [9, 9])
    from votacao.servicos import encerrar_votacao

    assert encerrar_votacao(edicao.pk) is None
    ensaio = cadastro.edicao(nome="Ensaio 2026/2")
    turma_e = cadastro.turma(ensaio, cadastro.curso("GTUR"))
    projeto_e = cadastro.projeto(turma_e, titulo="Do ensaio", status=Projeto.Status.PUBLICADO)
    Criterio.objects.create(edicao=ensaio, nome="C1", ordem=1)
    Criterio.objects.create(edicao=ensaio, nome="C2", ordem=2)
    from votacao.servicos import abrir_votacao

    assert abrir_votacao(ensaio.pk) is None
    fabricas.avaliar(fabricas.jurado(ensaio, turma_e), projeto_e, [1, 1])
    assert nota_banca_por_projeto(edicao) == {projetos[0].pk: Decimal("9")}
    assert nota_banca_por_projeto(ensaio) == {projeto_e.pk: Decimal("1")}


def test_premissa_toda_avaliacao_tem_os_n_criterios():
    edicao, turma, projetos = fabricas.cenario(criterios=3)
    jurado = fabricas.jurado(edicao, turma)
    for projeto in projetos:
        fabricas.avaliar(jurado, projeto, [6, 7, 8])
    n = Criterio.objects.filter(edicao=edicao).count()
    assert all(a.notas.count() == n for a in Avaliacao.objects.filter(jurado__edicao=edicao))


@pytest.mark.parametrize("quantidade", [2, 100])
def test_uma_consulta_so(quantidade):
    edicao, turma, projetos = fabricas.cenario(projetos=quantidade)
    jurado = fabricas.jurado(edicao, turma)
    for projeto in projetos:
        fabricas.avaliar(jurado, projeto, [7, 8])
    with CaptureQueriesContext(connection) as consultas:
        notas = nota_banca_por_projeto(edicao)
    assert len(notas) == quantidade
    assert len(consultas.captured_queries) == 1
