# Frente: Guilherme — spec 06 (ver TAREFAS.md).
from django.apps import AppConfig
from django.db.models.signals import post_migrate


class BancaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "banca"
    verbose_name = "Banca"

    def ready(self):
        from banca import sinais

        post_migrate.connect(sinais.criar_grupo_digitacao, sender=self)
