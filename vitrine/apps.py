# Frente: Cleiton — spec 02 (ver TAREFAS.md).
from django.apps import AppConfig


class VitrineConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "vitrine"
    verbose_name = "Vitrine pública"
