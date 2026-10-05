"""Regras da banca usadas fora do app (specs/06-avaliacao-banca.md)."""

from django.db.models import Avg

from cadastro.models import Edicao, Projeto
from banca.models import Nota


def nota_banca_por_projeto(edicao):
    """{projeto_id: Decimal} com a nota de banca de cada projeto publicado da
    edição que tem pelo menos uma avaliação (ADR-007).

    Regra: média dos critérios em cada avaliação, depois média entre os
    jurados. Toda avaliação tem exatamente os N critérios da edição
    (obrigatórios na digitação, travados antes dela), então a média das
    médias é a média de todas as notas do projeto: uma consulta só. Sem
    arredondamento (spec 04). Não olha `banca_conferida_em`.
    """
    linhas = (
        Nota.objects.filter(
            avaliacao__jurado__edicao=edicao,
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
