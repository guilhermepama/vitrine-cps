from django.contrib import admin

from cadastro.admin import SoSuperusuarioMixin
from cadastro.models import Projeto
from mapa.models import Local


@admin.register(Local)
class LocalAdmin(SoSuperusuarioMixin, admin.ModelAdmin):
    """Tela da montagem: tudo editável na lista, filtrada por edição e tipo."""

    list_display = ["codigo", "tipo", "rotulo", "nome", "aberta", "projeto", "edicao"]
    list_editable = ["rotulo", "nome", "aberta", "projeto"]
    list_filter = ["edicao", "tipo", "fileira", "aberta"]
    list_select_related = ["projeto", "edicao"]
    list_per_page = 100
    search_fields = ["codigo", "rotulo", "nome", "projeto__titulo"]
    readonly_fields = ["codigo", "tipo", "fileira", "ordem"]
    ordering = ["tipo", "fileira", "ordem", "codigo"]

    def has_add_permission(self, request, *args):
        return False  # pontos nascem do `semear_mapa`; o admin só preenche

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "projeto":
            kwargs["queryset"] = Projeto.objects.filter(turma__edicao__ativa=True).select_related("turma__curso").order_by("titulo")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
