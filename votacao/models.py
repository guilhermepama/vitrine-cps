"""Schema do credenciamento e da votação (specs/03-credenciamento-votacao.md)."""

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Func, Q, Value

from cadastro.models import Edicao, Projeto


def truncar_para_hora(momento):
    """Zera minutos, segundos e microssegundos (spec 03, "Cadastro do visitante").

    O fuso do projeto (−03:00) é de horas inteiras: truncar no fuso local ou
    em UTC dá o mesmo instante.
    """
    return momento.replace(minute=0, second=0, microsecond=0)


class Estacao(models.Model):
    nome = models.CharField(max_length=60)
    ativa = models.BooleanField(default=True)
    edicao = models.ForeignKey(Edicao, on_delete=models.PROTECT, related_name="estacoes")

    class Meta:
        db_table = "estacoes"
        verbose_name = "estação"
        verbose_name_plural = "estações"

    def __str__(self):
        return self.nome

    def clean(self):
        super().clean()
        self._verificar_travas()

    def save(self, *args, **kwargs):
        self._verificar_travas()
        super().save(*args, **kwargs)

    def _verificar_travas(self):
        """Estação que já emitiu token não muda de edição: os tokens iriam junto."""
        if not self.pk:
            return
        antes = Estacao.objects.filter(pk=self.pk).values_list("edicao_id", flat=True).first()
        if antes is not None and antes != self.edicao_id and self.tokens.exists():
            raise ValidationError({"edicao": "Estação que já emitiu token não muda de edição."})


class Token(models.Model):
    # Gerado no servidor (guardrail 1). A edição do token é a da estação.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    estacao = models.ForeignKey(Estacao, on_delete=models.PROTECT, related_name="tokens")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tokens"


class Voto(models.Model):
    token = models.ForeignKey(Token, on_delete=models.PROTECT, related_name="votos")
    projeto = models.ForeignKey(Projeto, on_delete=models.PROTECT, related_name="votos")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "votos"
        # Guardrail 4: a unicidade mora no banco, não só no código.
        constraints = [models.UniqueConstraint(fields=["token", "projeto"], name="voto_unico_por_token_projeto")]


class Visitante(models.Model):
    """Cadastro LGPD do visitante (guardrails 6, 9 e 10; ADR-003).

    Sem coluna de token, voto ou estação, e nenhum outro campo de data/hora.
    O id é UUID v4 para não revelar a ordem de cadastro (spec 03, P1).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nome = models.CharField(max_length=120)
    email = models.CharField(max_length=254)
    telefone = models.CharField(max_length=13, null=True, blank=True)
    consentimento_em = models.DateTimeField()
    edicao = models.ForeignKey(Edicao, on_delete=models.PROTECT, related_name="visitantes")

    class Meta:
        db_table = "visitantes"
        constraints = [
            # O save() trunca; o banco barra o que pula o save() (bulk_create, update()).
            models.CheckConstraint(
                condition=Q(
                    consentimento_em=Func(
                        Value("hour"), F("consentimento_em"), function="date_trunc", output_field=models.DateTimeField()
                    )
                ),
                name="consentimento_truncado_na_hora",
            ),
            models.CheckConstraint(condition=Q(telefone__regex=r"^[0-9]{10,13}$"), name="telefone_so_digitos"),
        ]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        if self.consentimento_em is not None:
            self.consentimento_em = truncar_para_hora(self.consentimento_em)
        super().save(*args, **kwargs)
