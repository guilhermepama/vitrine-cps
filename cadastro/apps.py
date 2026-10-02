# Frente: Guilherme — specs 01 e 05 (ver TAREFAS.md).
from django.apps import AppConfig


class CadastroConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cadastro"
    verbose_name = "Cadastro"
