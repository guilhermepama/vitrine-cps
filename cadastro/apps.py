# Frente: Guilherme — spec 01, que absorveu a 05 (ver TAREFAS.md).
from django.apps import AppConfig


class CadastroConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cadastro"
    verbose_name = "Cadastro"
