"""Dados fictícios para os testes da votação (reaproveitam os do cadastro)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from cadastro.tests import fabricas as cadastro
from votacao.models import Estacao, Token, Visitante, Voto

BRASILIA = ZoneInfo("America/Sao_Paulo")


def estacao(edicao_=None, nome="Entrada", **campos):
    return Estacao.objects.create(edicao=edicao_ or cadastro.edicao(), nome=nome, **campos)


def token(estacao_=None):
    return Token.objects.create(estacao=estacao_ or estacao())


def voto(token_=None, projeto_=None):
    """Sem argumentos, token e projeto ficam na mesma edição."""
    token_ = token_ or token()
    projeto_ = projeto_ or cadastro.projeto(cadastro.turma(token_.estacao.edicao))
    return Voto.objects.create(token=token_, projeto=projeto_)


def visitante(edicao_=None, **campos):
    padrao = {
        "nome": "Visitante Teste",
        "email": "visitante@example.com",
        "consentimento_em": datetime(2026, 10, 29, 19, 0, tzinfo=BRASILIA),
    }
    padrao.update(campos)
    return Visitante.objects.create(edicao=edicao_ or cadastro.edicao(), **padrao)
