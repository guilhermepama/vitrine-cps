"""Banca: critérios, jurados, avaliações e notas (specs/06-avaliacao-banca.md).

Jurado avalia em ficha impressa e a equipe digita no admin (ADR-008). Nada
aqui se liga a tokens, votos ou visitantes do público.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q

from cadastro.models import Edicao, Projeto, Turma


def _votacao_aberta(*edicao_ids, travar=False):
    """Alguma das edições já abriu a votação? Com `travar`, trava as linhas
    (em ordem de pk, sem deadlock) até o fim da transação."""
    ids = sorted({i for i in edicao_ids if i is not None})
    consulta = Edicao.objects.filter(pk__in=ids).order_by("pk")
    if travar:
        consulta = consulta.select_for_update()
    return any(aberta is not None for aberta in consulta.values_list("votacao_aberta_em", flat=True))


class Criterio(models.Model):
    edicao = models.ForeignKey(Edicao, on_delete=models.PROTECT, related_name="criterios_banca")
    nome = models.CharField(max_length=60)
    apoio = models.CharField(max_length=200, blank=True, help_text="Texto de apoio impresso na ficha.")
    ordem = models.PositiveSmallIntegerField()

    class Meta:
        verbose_name = "critério"
        ordering = ["edicao", "ordem"]
        constraints = [
            models.UniqueConstraint(fields=["edicao", "nome"], name="criterio_nome_unico_na_edicao"),
            models.UniqueConstraint(fields=["edicao", "ordem"], name="criterio_ordem_unica_na_edicao"),
            models.CheckConstraint(condition=Q(ordem__gte=1), name="criterio_ordem_positiva"),
        ]

    def __str__(self):
        return self.nome

    def clean(self):
        super().clean()
        self._verificar_trava()

    def save(self, *args, **kwargs):
        with transaction.atomic():
            self._verificar_trava(travar=True)
            super().save(*args, **kwargs)

    def _verificar_trava(self, travar=False):
        """Critérios são divulgados antes do evento (ADR-007): travados depois
        de aberta a votação, com a linha da `Edicao` travada no save(). Vale
        para a edição de destino e para a de origem (mover o critério tiraria
        um critério de uma edição aberta)."""
        antes = Criterio.objects.filter(pk=self.pk).values_list("edicao_id", flat=True).first() if self.pk else None
        if _votacao_aberta(self.edicao_id, antes, travar=travar):
            raise ValidationError("Os critérios não mudam depois de aberta a votação (ADR-007).")


class Jurado(models.Model):
    edicao = models.ForeignKey(Edicao, on_delete=models.PROTECT, related_name="jurados")
    nome = models.CharField(max_length=120)
    turmas = models.ManyToManyField(Turma, related_name="jurados", help_text="Turmas que o jurado avalia.")

    class Meta:
        ordering = ["edicao", "nome"]
        constraints = [models.UniqueConstraint(fields=["edicao", "nome"], name="jurado_nome_unico_na_edicao")]
        permissions = [
            ("imprimir_ficha", "Pode imprimir a ficha da banca"),
            ("concluir_conferencia", "Pode concluir a conferência da banca"),
        ]

    def __str__(self):
        return f"{self.edicao} · {self.nome}"


class Avaliacao(models.Model):
    """Uma linha da ficha: o que um jurado deu a um projeto."""

    jurado = models.ForeignKey(Jurado, on_delete=models.PROTECT, related_name="avaliacoes")
    projeto = models.ForeignKey(Projeto, on_delete=models.PROTECT, related_name="avaliacoes_banca")
    digitado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    digitado_em = models.DateTimeField(auto_now_add=True)
    alterado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    alterado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "avaliação"
        verbose_name_plural = "avaliações"
        constraints = [
            models.UniqueConstraint(
                fields=["jurado", "projeto"],
                name="avaliacao_unica_por_jurado_e_projeto",
                violation_error_message="Esta ficha já foi digitada; edite a existente.",
            )
        ]

    def __str__(self):
        return f"{self.jurado.nome} → #{self.projeto_id}"

    def clean(self):
        super().clean()
        if not (self.jurado_id and self.projeto_id):
            return
        jurado, projeto = self.jurado, self.projeto
        if projeto.turma.edicao_id != jurado.edicao_id:
            raise ValidationError("O projeto é de outra edição.")
        if not jurado.turmas.filter(pk=projeto.turma_id).exists():
            raise ValidationError("O projeto não é de uma turma deste jurado.")
        if projeto.status != Projeto.Status.PUBLICADO:
            raise ValidationError("O projeto não está publicado.")
        if not _votacao_aberta(jurado.edicao_id):
            raise ValidationError("A votação desta edição ainda não foi aberta.")
        if not Criterio.objects.filter(edicao_id=jurado.edicao_id).exists():
            raise ValidationError("A edição não tem critérios cadastrados.")

    def save(self, *args, **kwargs):
        # Atômico: o desfazer da conferência (sinais) entra na mesma transação.
        with transaction.atomic():
            super().save(*args, **kwargs)


class Nota(models.Model):
    avaliacao = models.ForeignKey(Avaliacao, on_delete=models.CASCADE, related_name="notas")
    criterio = models.ForeignKey(Criterio, on_delete=models.PROTECT, related_name="notas")
    valor = models.DecimalField(max_digits=3, decimal_places=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["avaliacao", "criterio"], name="nota_unica_por_avaliacao_e_criterio"),
            models.CheckConstraint(condition=Q(valor__gte=0) & Q(valor__lte=10), name="nota_entre_0_e_10"),
        ]

    def __str__(self):
        return f"{self.criterio}: {self.valor}"

    def clean(self):
        super().clean()
        # A avaliação pode ainda não estar salva (inline do "Adicionar").
        avaliacao = self._state.fields_cache.get("avaliacao") or (
            Avaliacao.objects.filter(pk=self.avaliacao_id).first() if self.avaliacao_id else None
        )
        if avaliacao and avaliacao.jurado_id and self.criterio_id:
            if self.criterio.edicao_id != avaliacao.jurado.edicao_id:
                raise ValidationError("O critério é de outra edição.")

    def save(self, *args, **kwargs):
        with transaction.atomic():
            super().save(*args, **kwargs)
