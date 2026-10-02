# Frente: Renan — spec 03 (ver TAREFAS.md).
from django.apps import AppConfig


class VotacaoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "votacao"
    verbose_name = "Credenciamento e votação"
