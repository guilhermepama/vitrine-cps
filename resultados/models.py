"""Schema próprio do app resultados (specs/04-resultados.md, "Dados").

Só um model sem tabela para declarar as permissões do app. O resultados é
somente leitura sobre os dados do cadastro, da votação e da banca.
"""

from django.db import models


class PermissaoResultados(models.Model):
    """Sem tabela (`managed = False`) e sem as permissões padrão de model:
    existe só para a migration registrar as duas permissões abaixo."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("ver_resultados", "Pode ver o ranking e os relatórios de resultados"),
            ("exportar_visitantes", "Pode exportar a lista de visitantes"),
        ]
        verbose_name = "permissão de resultados"
        verbose_name_plural = "permissões de resultados"
