"""Corrigir nota depois da conferência apaga `banca_conferida_em` (spec 01 e 06).

post_save/post_delete, e não o save()/delete() dos models: o `post_delete` é
enviado por objeto também no `queryset.delete()` (exclusão em lote do admin)
e nas `Nota` apagadas em cascata, sempre dentro da transação da exclusão.
"""

from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from banca.models import Avaliacao, Nota
from banca.servicos import desfazer_conferencia

GRUPO_DIGITACAO = "digitacao-banca"
PERMISSOES_DIGITACAO = [
    ("avaliacao", "add"),
    ("avaliacao", "change"),
    ("avaliacao", "view"),
    ("nota", "add"),
    ("nota", "change"),
    ("nota", "view"),
    ("jurado", "view"),
    ("criterio", "view"),
]


def _edicao_da_avaliacao(avaliacao_id):
    return Avaliacao.objects.filter(pk=avaliacao_id).values_list("jurado__edicao_id", flat=True).first()


@receiver(post_save, sender=Avaliacao)
def _avaliacao_salva(sender, instance, created, raw=False, **kwargs):
    if not raw and (created or instance.mudou()):
        desfazer_conferencia(instance.jurado.edicao_id)


@receiver(post_save, sender=Nota)
def _nota_salva(sender, instance, created, raw=False, **kwargs):
    if not raw and (created or instance.mudou()):
        desfazer_conferencia(_edicao_da_avaliacao(instance.avaliacao_id))


@receiver(post_delete, sender=Avaliacao)
def _avaliacao_apagada(sender, instance, **kwargs):
    desfazer_conferencia(instance.jurado.edicao_id)


@receiver(post_delete, sender=Nota)
def _nota_apagada(sender, instance, **kwargs):
    # Na cascata, a avaliação já pode ter saído; a dela desfaz do mesmo jeito.
    edicao_id = _edicao_da_avaliacao(instance.avaliacao_id)
    if edicao_id is not None:
        desfazer_conferencia(edicao_id)


def criar_grupo_digitacao(sender, **kwargs):
    """post_migrate: as Permission só existem depois dele (uma data migration
    não as acharia num banco novo). Idempotente: o grupo fica com exatamente
    estas permissões."""
    permissoes = [
        Permission.objects.get(content_type__app_label="banca", content_type__model=model, codename=f"{acao}_{model}")
        for model, acao in PERMISSOES_DIGITACAO
    ]
    grupo, _ = Group.objects.get_or_create(name=GRUPO_DIGITACAO)
    grupo.permissions.set(permissoes)
