"""Dados fictícios para os testes da banca."""

from decimal import Decimal

from django.contrib.auth import get_user_model

from banca.models import Avaliacao, Criterio, Jurado, Nota
from cadastro.models import Projeto
from cadastro.tests import fabricas as cadastro
from votacao.servicos import abrir_votacao

PUBLICADO = Projeto.Status.PUBLICADO


def digitador(username="barbara"):
    return get_user_model().objects.get_or_create(username=username)[0]


def cenario(criterios=2, projetos=2):
    """Edição com critérios, uma turma com projetos publicados, votação aberta."""
    edicao = cadastro.edicao()
    turma = cadastro.turma(edicao)
    lista = [cadastro.projeto(turma, titulo=f"Projeto {i}", status=PUBLICADO) for i in range(projetos)]
    for i in range(criterios):
        Criterio.objects.create(edicao=edicao, nome=f"Critério {i + 1}", ordem=i + 1)
    assert abrir_votacao(edicao.pk) is None
    edicao.refresh_from_db()
    return edicao, turma, lista


def jurado(edicao, turma, nome="Ana"):
    j = Jurado.objects.create(edicao=edicao, nome=nome)
    j.turmas.add(turma)
    return j


def avaliar(jurado_, projeto, valores, usuario=None):
    avaliacao = Avaliacao.objects.create(jurado=jurado_, projeto=projeto, digitado_por=usuario or digitador())
    for criterio, valor in zip(Criterio.objects.filter(edicao=jurado_.edicao), valores, strict=True):
        Nota.objects.create(avaliacao=avaliacao, criterio=criterio, valor=Decimal(str(valor)))
    return avaliacao
