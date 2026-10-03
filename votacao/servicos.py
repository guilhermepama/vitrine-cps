"""Abertura e encerramento da votação (spec 03, "Abrir e encerrar").

Os campos de votação da `Edicao` mudam só por `save()` na instância travada,
nunca por `QuerySet.update()`/`bulk_update`, que passariam por cima das
travas do cadastro (regra do PR #17).
"""

from django.db import transaction
from django.utils import timezone

from cadastro.models import Edicao

JA_EXISTE_VOTACAO_ABERTA = "Já existe uma votação aberta ({}). Encerre-a antes de abrir outra."
JA_FOI_ABERTA = "A votação desta edição já foi aberta e não pode ser reaberta."
NAO_FOI_ABERTA = "A votação desta edição ainda não foi aberta."
JA_FOI_ENCERRADA = "A votação desta edição já foi encerrada."


def _em_votacao(edicao):
    return edicao.votacao_aberta_em is not None and edicao.votacao_encerrada_em is None


def edicao_em_votacao(travar=False):
    """Edição aberta e não encerrada, ou None. Sempre lida do banco, nunca do cliente.

    Com `travar=True`, trava a linha até o fim da transação (`select_for_update`)
    e precisa ser chamada dentro de `transaction.atomic()`.
    """
    consulta = Edicao.objects.filter(votacao_aberta_em__isnull=False, votacao_encerrada_em__isnull=True)
    if travar:
        consulta = consulta.select_for_update()
    return consulta.first()


def abrir_votacao(edicao_id):
    """Abre a votação da edição. Devolve a mensagem de recusa ou None."""
    with transaction.atomic():
        # Trava todas as edições, sempre na mesma ordem (sem deadlock): duas
        # aberturas simultâneas se enfileiram e a segunda vê a primeira (G4).
        edicoes = list(Edicao.objects.select_for_update().order_by("pk"))
        edicao = next((e for e in edicoes if e.pk == edicao_id), None)
        if edicao is None:
            raise Edicao.DoesNotExist(edicao_id)
        outra = next((e for e in edicoes if e.pk != edicao_id and _em_votacao(e)), None)
        if outra is not None:
            return JA_EXISTE_VOTACAO_ABERTA.format(outra)
        if edicao.votacao_aberta_em is not None:
            return JA_FOI_ABERTA
        edicao.votacao_aberta_em = timezone.now()
        edicao.save(update_fields=["votacao_aberta_em"])
    return None


def encerrar_votacao(edicao_id):
    """Encerra a votação da edição. Devolve a mensagem de recusa ou None."""
    with transaction.atomic():
        edicao = Edicao.objects.select_for_update().get(pk=edicao_id)
        if edicao.votacao_aberta_em is None:
            return NAO_FOI_ABERTA
        if edicao.votacao_encerrada_em is not None:
            return JA_FOI_ENCERRADA
        edicao.votacao_encerrada_em = timezone.now()
        edicao.save(update_fields=["votacao_encerrada_em"])
    return None
