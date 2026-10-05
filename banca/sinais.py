"""Corrigir nota depois da conferência apaga `banca_conferida_em` (spec 01 e 06).

post_save/post_delete, e não o save()/delete() dos models: o `post_delete` é
enviado por objeto também no `queryset.delete()` (exclusão em lote do admin)
e nas `Nota` apagadas em cascata, sempre dentro da transação da exclusão.
"""

from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from banca.models import Avaliacao, Jurado, Nota
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


def _edicao_do_jurado(jurado_id):
    return Jurado.objects.filter(pk=jurado_id).values_list("edicao_id", flat=True).first()


def _desfazer(*edicao_ids):
    for edicao_id in sorted({i for i in edicao_ids if i is not None}):
        desfazer_conferencia(edicao_id)


# O "antes" vem do banco no pre_save (dentro da transação do save atômico),
# não de um retrato da instância: instância velha ou com campos adiados não
# engana a comparação.


@receiver(pre_save, sender=Avaliacao)
def _avaliacao_antes(sender, instance, raw=False, **kwargs):
    instance._antes = (
        None
        if raw or instance._state.adding
        else Avaliacao.objects.filter(pk=instance.pk).values("jurado_id", "projeto_id").first()
    )


@receiver(post_save, sender=Avaliacao)
def _avaliacao_salva(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    antes = getattr(instance, "_antes", None)
    agora = {"jurado_id": instance.jurado_id, "projeto_id": instance.projeto_id}
    if created or antes is None or antes != agora:
        # Mudou de jurado: a edição de origem também deixa de estar conferida.
        _desfazer(_edicao_do_jurado(instance.jurado_id), antes and _edicao_do_jurado(antes["jurado_id"]))


@receiver(pre_save, sender=Nota)
def _nota_antes(sender, instance, raw=False, **kwargs):
    instance._antes = (
        None
        if raw or instance._state.adding
        else Nota.objects.filter(pk=instance.pk).values("avaliacao_id", "criterio_id", "valor").first()
    )


@receiver(post_save, sender=Nota)
def _nota_salva(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    antes = getattr(instance, "_antes", None)
    agora = {"avaliacao_id": instance.avaliacao_id, "criterio_id": instance.criterio_id, "valor": instance.valor}
    if created or antes is None or antes != agora:
        _desfazer(
            _edicao_da_avaliacao(instance.avaliacao_id), antes and _edicao_da_avaliacao(antes["avaliacao_id"])
        )


@receiver(post_delete, sender=Avaliacao)
def _avaliacao_apagada(sender, instance, **kwargs):
    _desfazer(_edicao_do_jurado(instance.jurado_id))


@receiver(post_delete, sender=Nota)
def _nota_apagada(sender, instance, **kwargs):
    # Na cascata, as notas saem antes da avaliação: ela ainda é encontrada.
    _desfazer(_edicao_da_avaliacao(instance.avaliacao_id))


@receiver(m2m_changed, sender=Jurado.turmas.through)
def _turma_do_jurado(sender, instance, action, reverse, pk_set, **kwargs):
    """Jurado não perde turma em que já avaliou, por qualquer caminho
    (`remove`, `set`, `clear`, pelo jurado ou pela turma)."""
    if action not in ("pre_remove", "pre_clear"):
        return
    avaliacoes = Avaliacao.objects.all()
    if reverse:  # turma.jurados.remove(...)
        avaliacoes = avaliacoes.filter(projeto__turma=instance)
        if action == "pre_remove":
            avaliacoes = avaliacoes.filter(jurado_id__in=pk_set)
    else:
        avaliacoes = avaliacoes.filter(jurado=instance)
        if action == "pre_remove":
            avaliacoes = avaliacoes.filter(projeto__turma_id__in=pk_set)
    if avaliacoes.exists():
        raise ValidationError("Jurado com avaliação digitada não perde a turma em que avaliou.")


def criar_grupo_digitacao(sender, **kwargs):
    """post_migrate: as Permission só existem depois dele (uma data migration
    não as acharia num banco novo). Idempotente: o grupo fica com exatamente
    estas permissões."""
    usando = kwargs.get("using", "default")
    estado = kwargs.get("apps")
    if estado is not None:
        try:  # `migrate <outro app>` num banco novo: a banca ainda não existe
            estado.get_model("banca", "Avaliacao")
            estado.get_model("auth", "Group")
        except LookupError:
            return
    codenames = {f"{acao}_{model}" for model, acao in PERMISSOES_DIGITACAO}
    permissoes = list(
        Permission.objects.using(usando).filter(content_type__app_label="banca", codename__in=codenames)
    )
    if len(permissoes) != len(codenames):
        return  # permissões ainda não criadas; o próximo migrate completo cria o grupo
    grupo, _ = Group.objects.using(usando).get_or_create(name=GRUPO_DIGITACAO)
    grupo.permissions.set(permissoes)
