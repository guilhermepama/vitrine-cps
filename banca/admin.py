"""Admin da banca: critérios e jurados (spec 06, fatia 2).

Quem altera é o superusuário (permissões padrão do model). O grupo
`digitacao-banca` só vê critérios e jurados (permissão `view`): o admin mostra
somente leitura e responde 403 a qualquer alteração.
"""

from django import forms
from django.contrib import admin

from banca.models import Avaliacao, Criterio, Jurado
from cadastro.models import Turma


def _votacao_aberta(edicao):
    return edicao is not None and edicao.votacao_aberta_em is not None


@admin.register(Criterio)
class CriterioAdmin(admin.ModelAdmin):
    list_display = ["nome", "edicao", "ordem"]
    list_filter = ["edicao"]
    ordering = ["edicao", "ordem"]
    fields = ["edicao", "nome", "apoio", "ordem"]

    def get_actions(self, request):
        # Sem "apagar selecionados": a exclusão em lote passaria por cima da trava.
        acoes = super().get_actions(request)
        acoes.pop("delete_selected", None)
        return acoes

    def has_change_permission(self, request, obj=None):
        # Edição com votação aberta: critério fica só para leitura (ADR-007).
        if obj is not None and _votacao_aberta(obj.edicao):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and _votacao_aberta(obj.edicao):
            return False
        return super().has_delete_permission(request, obj)


class TurmaComEdicao(forms.ModelMultipleChoiceField):
    def label_from_instance(self, turma):
        return f"{turma.edicao} · {turma.rotulo}"


class JuradoForm(forms.ModelForm):
    turmas = TurmaComEdicao(
        queryset=Turma.objects.select_related("edicao", "curso").order_by("edicao__nome", "curso__sigla"),
        widget=admin.widgets.FilteredSelectMultiple("turmas", is_stacked=False),
    )

    class Meta:
        model = Jurado
        fields = ["edicao", "nome", "turmas"]

    def clean(self):
        dados = super().clean()
        edicao, turmas = dados.get("edicao"), dados.get("turmas")
        if edicao is None or turmas is None:
            return dados
        if any(turma.edicao_id != edicao.pk for turma in turmas):
            raise forms.ValidationError("Todas as turmas do jurado têm de ser da edição dele.")
        if self.instance.pk:
            self._verificar_travas(edicao, turmas)
        return dados

    def _verificar_travas(self, edicao, turmas):
        """Jurado com avaliação não muda de edição nem perde turma onde já avaliou."""
        avaliadas = set(
            Avaliacao.objects.filter(jurado=self.instance).values_list("projeto__turma_id", flat=True)
        )
        if not avaliadas:
            return
        if edicao.pk != Jurado.objects.filter(pk=self.instance.pk).values_list("edicao_id", flat=True).get():
            raise forms.ValidationError("Jurado com avaliação digitada não muda de edição.")
        if avaliadas - {turma.pk for turma in turmas}:
            raise forms.ValidationError("Jurado com avaliação digitada não perde a turma em que avaliou.")


@admin.register(Jurado)
class JuradoAdmin(admin.ModelAdmin):
    form = JuradoForm
    list_display = ["nome", "edicao", "lista_turmas"]
    list_filter = ["edicao"]
    search_fields = ["nome"]

    @admin.display(description="turmas")
    def lista_turmas(self, jurado):
        return ", ".join(turma.rotulo for turma in jurado.turmas.all())

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("edicao").prefetch_related("turmas__curso")

    def get_actions(self, request):
        acoes = super().get_actions(request)
        acoes.pop("delete_selected", None)
        return acoes

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.avaliacoes.exists():
            return False
        return super().has_delete_permission(request, obj)
