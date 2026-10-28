"""Conteúdo do mapa do evento (spec 08, ADR-015). A geometria está em `planta.py`."""

from django.db import models

from cadastro.models import Edicao, Projeto


class Local(models.Model):
    class Tipo(models.TextChoices):
        ESTANDE = "estande", "estande"
        SALA = "sala", "sala"
        SERVICO = "servico", "serviço"
        ESTACAO = "estacao", "estação de QR"
        ENTRADA = "entrada", "entrada"

    edicao = models.ForeignKey(Edicao, on_delete=models.PROTECT, related_name="locais")
    codigo = models.SlugField(max_length=20, help_text="Chave do ponto na planta (mapa/planta.py). Não muda.")
    tipo = models.CharField(max_length=8, choices=Tipo.choices)
    fileira = models.CharField(max_length=1, blank=True)
    ordem = models.PositiveSmallIntegerField(default=0)
    rotulo = models.CharField(max_length=20, blank=True, help_text="O que o visitante lê no mapa: A3, Sala 12…")
    nome = models.CharField(max_length=80, blank=True, help_text="Atração da sala ou nome do serviço.")
    descricao = models.CharField(max_length=200, blank=True)
    aberta = models.BooleanField(default=True, help_text="Porta aberta ao público no evento.")
    projeto = models.ForeignKey(
        Projeto, on_delete=models.SET_NULL, null=True, blank=True, related_name="locais", help_text="Só em estande."
    )

    class Meta:
        db_table = "mapa_locais"
        verbose_name = "local do mapa"
        verbose_name_plural = "locais do mapa"
        ordering = ["tipo", "fileira", "ordem", "codigo"]
        constraints = [
            models.UniqueConstraint(fields=["edicao", "codigo"], name="local_unico_por_edicao"),
            # Um projeto fica em um estande só.
            models.UniqueConstraint(fields=["edicao", "projeto"], name="projeto_em_um_estande", condition=models.Q(projeto__isnull=False)),
        ]

    def __str__(self):
        return self.rotulo or self.codigo

    @property
    def nome_publico(self):
        """O que aparece como atração: só com a porta aberta."""
        return self.nome if self.aberta else ""
