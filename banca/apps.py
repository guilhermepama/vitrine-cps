# Frente: Guilherme — spec 06 (ver TAREFAS.md).
from django.apps import AppConfig


class BancaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "banca"
    verbose_name = "Banca"
