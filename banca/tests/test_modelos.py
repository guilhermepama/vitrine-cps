"""Critérios de aceite "Modelo" da spec 06."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from banca.models import Avaliacao, Criterio, Jurado, Nota
from banca.tests import fabricas
from cadastro.models import Projeto
from cadastro.tests import fabricas as cadastro

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario():
    edicao, turma, projetos = fabricas.cenario()
    jurado = fabricas.jurado(edicao, turma)
    return edicao, turma, projetos, jurado


def _erro_de_integridade(funcao):
    with pytest.raises(IntegrityError), transaction.atomic():
        funcao()


def test_nota_repetida_no_mesmo_criterio(cenario):
    _, _, projetos, jurado = cenario
    avaliacao = fabricas.avaliar(jurado, projetos[0], [7, 8])
    criterio = avaliacao.notas.first().criterio
    _erro_de_integridade(lambda: Nota.objects.create(avaliacao=avaliacao, criterio=criterio, valor=5))


def test_avaliacao_repetida_para_o_mesmo_jurado_e_projeto(cenario):
    _, _, projetos, jurado = cenario
    fabricas.avaliar(jurado, projetos[0], [7, 8])
    _erro_de_integridade(
        lambda: Avaliacao.objects.create(jurado=jurado, projeto=projetos[0], digitado_por=fabricas.digitador())
    )


def test_mensagem_da_avaliacao_repetida(cenario):
    _, _, projetos, jurado = cenario
    fabricas.avaliar(jurado, projetos[0], [7, 8])
    with pytest.raises(ValidationError, match="já foi digitada"):
        Avaliacao(jurado=jurado, projeto=projetos[0], digitado_por=fabricas.digitador()).validate_constraints()


@pytest.mark.parametrize("valor", ["10.1", "-0.1"])
def test_nota_fora_de_0_a_10_no_banco(cenario, valor):
    _, _, projetos, jurado = cenario
    avaliacao = Avaliacao.objects.create(jurado=jurado, projeto=projetos[0], digitado_por=fabricas.digitador())
    criterio = Criterio.objects.filter(edicao=jurado.edicao).first()
    _erro_de_integridade(lambda: Nota.objects.create(avaliacao=avaliacao, criterio=criterio, valor=Decimal(valor)))


@pytest.mark.parametrize("campos", [{"nome": "Repetido", "ordem": 9}, {"nome": "Outro", "ordem": 1}, {"nome": "Zero", "ordem": 0}])
def test_criterio_repetido_ou_ordem_zero(campos):
    edicao = cadastro.edicao()
    Criterio.objects.create(edicao=edicao, nome="Repetido", ordem=1)
    _erro_de_integridade(lambda: Criterio.objects.create(edicao=edicao, **campos))


def test_criterio_travado_depois_de_aberta_a_votacao(cenario):
    edicao = cenario[0]
    criterio = Criterio.objects.filter(edicao=edicao).first()
    criterio.nome = "Outro nome"
    with pytest.raises(ValidationError):
        criterio.save()
    with pytest.raises(ValidationError):
        Criterio.objects.create(edicao=edicao, nome="Novo", ordem=9)
    with pytest.raises(ValidationError):
        criterio.full_clean()
    assert list(Criterio.objects.filter(edicao=edicao).values_list("nome", flat=True)) == ["Critério 1", "Critério 2"]


def test_criterio_e_jurado_com_nota_nao_sao_apagados(cenario):
    _, _, projetos, jurado = cenario
    avaliacao = fabricas.avaliar(jurado, projetos[0], [7, 8])
    with pytest.raises(ProtectedError):
        avaliacao.notas.first().criterio.delete()
    with pytest.raises(ProtectedError):
        Jurado.objects.get(pk=jurado.pk).delete()


def _avaliacao(jurado, projeto):
    return Avaliacao(jurado=jurado, projeto=projeto, digitado_por=fabricas.digitador())


def test_avaliacao_valida_passa_no_clean(cenario):
    _, _, projetos, jurado = cenario
    _avaliacao(jurado, projetos[0]).full_clean()


def test_projeto_de_outra_edicao_ou_fora_das_turmas(cenario):
    edicao, _, _, jurado = cenario
    outra_turma = cadastro.turma(edicao, cadastro.curso("GTUR"))
    fora = cadastro.projeto(outra_turma, titulo="Fora", status=Projeto.Status.PUBLICADO)
    with pytest.raises(ValidationError, match="turma deste jurado"):
        _avaliacao(jurado, fora).full_clean()
    outra = cadastro.edicao(nome="Ensaio 2026/2")
    de_outra = cadastro.projeto(cadastro.turma(outra, cadastro.curso("ADS")), titulo="Outra edição")
    with pytest.raises(ValidationError, match="outra edição"):
        _avaliacao(jurado, de_outra).full_clean()


def test_projeto_nao_publicado():
    edicao = cadastro.edicao()
    turma = cadastro.turma(edicao)
    rascunho = cadastro.projeto(turma)
    Criterio.objects.create(edicao=edicao, nome="C", ordem=1)
    jurado = fabricas.jurado(edicao, turma)
    with pytest.raises(ValidationError, match="não está publicado"):
        _avaliacao(jurado, rascunho).full_clean()


def test_votacao_nao_aberta_e_edicao_sem_criterios():
    edicao = cadastro.edicao()
    turma = cadastro.turma(edicao)
    projeto = cadastro.projeto(turma, status=Projeto.Status.PUBLICADO)
    jurado = fabricas.jurado(edicao, turma)
    with pytest.raises(ValidationError, match="ainda não foi aberta"):
        _avaliacao(jurado, projeto).full_clean()
    from votacao.servicos import abrir_votacao

    assert abrir_votacao(edicao.pk) is None
    with pytest.raises(ValidationError, match="sem critérios|não tem critérios"):
        _avaliacao(jurado, projeto).full_clean()


def test_nota_de_criterio_de_outra_edicao(cenario):
    _, _, projetos, jurado = cenario
    avaliacao = Avaliacao.objects.create(jurado=jurado, projeto=projetos[0], digitado_por=fabricas.digitador())
    alheio = Criterio.objects.create(edicao=cadastro.edicao(nome="Outra"), nome="X", ordem=1)
    with pytest.raises(ValidationError, match="outra edição"):
        Nota(avaliacao=avaliacao, criterio=alheio, valor=5).full_clean()


def test_mover_criterio_de_edicao_aberta_e_recusado(cenario):
    edicao = cenario[0]
    criterio = Criterio.objects.filter(edicao=edicao).first()
    criterio.edicao = cadastro.edicao(nome="Fechada")
    with pytest.raises(ValidationError):
        criterio.full_clean()
    with pytest.raises(ValidationError):
        criterio.save()
    assert Criterio.objects.filter(edicao=edicao).count() == 2


def test_nota_de_criterio_de_outra_edicao_com_avaliacao_ainda_nao_salva(cenario):
    _, _, projetos, jurado = cenario
    avaliacao = Avaliacao(jurado=jurado, projeto=projetos[0], digitado_por=fabricas.digitador())
    alheio = Criterio.objects.create(edicao=cadastro.edicao(nome="Outra"), nome="X", ordem=1)
    with pytest.raises(ValidationError, match="outra edição"):
        Nota(avaliacao=avaliacao, criterio=alheio, valor=5).clean()
