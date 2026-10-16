"""Regras da banca usadas fora do app (specs/06-avaliacao-banca.md)."""

from django.db.models import Avg

from cadastro.models import Edicao, Projeto
from banca.models import Nota, Tipo


def nota_banca_por_projeto(edicao, tipo=Tipo.BANCA):
    """{projeto_id: Decimal} com a nota de cada projeto publicado da edição que
    tem pelo menos uma avaliação do `tipo` (ADR-007; ADR-013: `banca` ou
    `convidado`, cada um com seus critérios)."""
    return _nota_por_projeto(edicao, tipo)


def _nota_por_projeto(edicao, tipo):
    """Nota de um tipo de avaliador por projeto (ADR-007).

    Regra: média dos critérios em cada avaliação, depois média entre os
    jurados do tipo. Toda avaliação tem exatamente os N critérios do tipo na edição
    (obrigatórios na digitação, travados antes dela), então a média das
    médias é a média de todas as notas do projeto: uma consulta só. Sem
    arredondamento (spec 04). Não olha `banca_conferida_em`.
    """
    linhas = (
        Nota.objects.filter(
            avaliacao__jurado__edicao=edicao,
            avaliacao__jurado__tipo=tipo,
            avaliacao__projeto__turma__edicao=edicao,
            avaliacao__projeto__status=Projeto.Status.PUBLICADO,
        )
        .values("avaliacao__projeto_id")
        .annotate(media=Avg("valor"))
    )
    return {linha["avaliacao__projeto_id"]: linha["media"] for linha in linhas}


def desfazer_conferencia(edicao_id):
    """Apaga `banca_conferida_em`, com a linha da `Edicao` travada.

    Chamado dentro da transação de quem alterou a nota (sinais). Devolve True
    se havia conferência a desfazer.
    """
    edicao = Edicao.objects.select_for_update().get(pk=edicao_id)
    if edicao.banca_conferida_em is None:
        return False
    edicao.banca_conferida_em = None
    edicao.save(update_fields=["banca_conferida_em"])
    return True
