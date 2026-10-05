"""Admin da banca (spec 06): critérios e jurados (fatia 2) e digitação (fatia 3).

Critérios e jurados: quem altera é o superusuário (permissões padrão do
model); o grupo `digitacao-banca` só vê. Avaliações: o grupo cria e altera,
só o superusuário apaga.
"""

import re
from urllib.parse import urlsplit, urlunsplit

from django import forms
from django.contrib import admin, messages
from django.db import IntegrityError
from django.forms.models import BaseInlineFormSet
from django.http import HttpResponseRedirect, QueryDict
from django.utils import timezone
from django.utils.html import format_html

from banca.models import Avaliacao, Criterio, Jurado, Nota
from cadastro.models import Edicao, Projeto, Turma


def _edicao_aberta(edicao):
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
        if obj is not None and _edicao_aberta(obj.edicao):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and _edicao_aberta(obj.edicao):
            return False
        return super().has_delete_permission(request, obj)


class TurmaComEdicao(forms.ModelMultipleChoiceField):
    def label_from_instance(self, turma):
        return f"{turma.edicao} · {turma.rotulo}"


class JuradoForm(forms.ModelForm):
    turmas = TurmaComEdicao(
        queryset=Turma.objects.select_related("edicao", "curso").order_by(
            "edicao__nome", "curso__sigla", "numero_periodo", "turno"
        ),
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


# --- Digitação das fichas (fatia 3) ---------------------------------------------------------

CONFERENCIA_DESFEITA = "A conferência desta edição foi desfeita; confira de novo."


def _jurados_digitaveis():
    """Jurados de edições que já abriram a votação (antes disso turma e status
    dos projetos ainda mudam) e cuja banca não foi conferida (decisão do
    coordenador no #55: edição antiga ou ensaio não recebem ficha nova por
    engano). Encerrada continua valendo: digita-se no dia 30."""
    return Jurado.objects.filter(
        edicao__votacao_aberta_em__isnull=False, edicao__banca_conferida_em__isnull=True
    ).select_related("edicao")


def _jurado_da_url(request):
    """Jurado do `?jurado=<id>`, se for válido; senão None (volta ao passo 1)."""
    if not hasattr(request, "_banca_jurado"):
        valor = request.GET.get("jurado", "")
        valido = valor.isascii() and valor.isdigit()
        request._banca_jurado = _jurados_digitaveis().filter(pk=valor).first() if valido else None
    return request._banca_jurado


def _conferida(edicao_id):
    return Edicao.objects.filter(pk=edicao_id, banca_conferida_em__isnull=False).exists()


class EscolherJuradoForm(forms.ModelForm):
    """Passo 1: só o jurado. Nunca grava: o add_view redireciona para o passo 2."""

    jurado = forms.ModelChoiceField(queryset=_jurados_digitaveis(), label="Jurado")

    class Meta:
        model = Avaliacao
        fields = ["jurado"]


class ProjetoDaFicha(forms.ModelChoiceField):
    def label_from_instance(self, projeto):
        return f"#{projeto.pk} — {projeto.titulo} ({projeto.turma.rotulo})"


def _form_da_ficha(escolhido):
    """Passo 2: jurado fixo (disabled: o POST não o muda, e o par (jurado,
    projeto) continua no formulário para a validação da duplicata)."""
    projetos = Projeto.objects.filter(
        turma__jurados=escolhido, turma__edicao_id=escolhido.edicao_id, status=Projeto.Status.PUBLICADO
    ).select_related("turma__curso")

    class AvaliacaoForm(forms.ModelForm):
        jurado = forms.ModelChoiceField(
            queryset=Jurado.objects.filter(pk=escolhido.pk), initial=escolhido.pk, disabled=True, label="Jurado"
        )
        projeto = ProjetoDaFicha(queryset=projetos.order_by("turma", "titulo"), label="Projeto")

        class Meta:
            model = Avaliacao
            fields = ["jurado", "projeto"]

    return AvaliacaoForm


class CriterioFixo(forms.HiddenInput):
    """O critério da linha vai oculto no POST e aparece como texto."""

    @property
    def is_hidden(self):
        return False  # a coluna aparece no inline tabular

    def render(self, name, value, attrs=None, renderer=None):
        nomes = {str(chave): rotulo for chave, rotulo in self.choices}
        return format_html("{}{}", super().render(name, value, attrs, renderer), nomes.get(str(value), ""))


FORMATO_NOTA = re.compile(r"\d{1,2}([,.]\d)?", re.ASCII)


class NotaDaFicha(forms.DecimalField):
    """Só o que se escreve numa ficha: "7", "7,5" (ou "7.5"). Recusa o que o
    Decimal aceitaria por acaso: 1e1, 1_0, dígitos de largura total, "7,", ",5"."""

    def to_python(self, value):
        if isinstance(value, str):
            value = value.strip()
            if value and not FORMATO_NOTA.fullmatch(value):
                raise forms.ValidationError("Use de 0 a 10, com no máximo uma casa decimal (ex.: 7,5).")
        return super().to_python(value)


class NotaForm(forms.ModelForm):
    valor = NotaDaFicha(max_digits=3, decimal_places=1, max_value=10, localize=True, label="Nota (0 a 10)")

    class Meta:
        model = Nota
        fields = ["criterio", "valor"]
        widgets = {"criterio": CriterioFixo}


def _criterios_do(jurado):
    return Criterio.objects.filter(edicao_id=jurado.edicao_id) if jurado else Criterio.objects.none()


class NotasFormSet(BaseInlineFormSet):
    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(i, **kwargs)
        form.fields["criterio"].queryset = self._criterios()
        return form

    def _criterios(self):
        return _criterios_do(self.instance.jurado if self.instance.jurado_id else None)

    def clean(self):
        """Uma nota por critério da edição do jurado, nem mais nem menos
        (protege contra POST adulterado)."""
        if self.instance.jurado_id:  # antes do super(): duplicata cai aqui, com a mensagem da ficha
            enviados = [getattr(form, "cleaned_data", {}).get("criterio") for form in self.forms]
            esperados = sorted(self._criterios().values_list("pk", flat=True))
            if None in enviados or sorted(c.pk for c in enviados) != esperados:
                raise forms.ValidationError("A ficha tem de ter uma nota para cada critério da edição do jurado.")
        self._conferir_linhas_gravadas()
        super().clean()

    def _conferir_linhas_gravadas(self):
        """POST adulterado: as linhas "existentes" têm de ser exatamente as notas
        desta avaliação (nenhuma na criação), sem id repetido nem alheio, e o
        critério de uma nota gravada não muda."""
        gravadas = self.get_queryset().values_list("pk", flat=True) if self.instance.pk else []
        enviadas = [form.instance.pk for form in self.initial_forms]  # pk None: id alheio
        if sorted(map(str, enviadas)) != sorted(map(str, gravadas)) or any(
            "criterio" in form.changed_data for form in self.initial_forms
        ):
            raise forms.ValidationError("As linhas da ficha não conferem com as notas gravadas desta avaliação.")


class NotaInline(admin.TabularInline):
    model = Nota
    form = NotaForm
    formset = NotasFormSet
    extra = 0
    can_delete = False

    def _jurado(self, request, obj):
        return obj.jurado if obj is not None else _jurado_da_url(request)

    def get_min_num(self, request, obj=None, **kwargs):
        jurado = self._jurado(request, obj)
        cache = request.__dict__.setdefault("_banca_n_criterios", {})
        if jurado not in cache:
            cache[jurado] = _criterios_do(jurado).count()
        return cache[jurado]

    get_max_num = get_min_num

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("criterio").order_by("criterio__ordem")

    def get_formset(self, request, obj=None, **kwargs):
        return super().get_formset(request, obj, validate_min=True, validate_max=True, **kwargs)


class JuradoFiltro(admin.SimpleListFilter):
    """Jurados com avaliação, numa consulta só (o filtro padrão lia a edição de
    cada jurado para o rótulo)."""

    title = "jurado"
    parameter_name = "jurado__id__exact"

    def lookups(self, request, model_admin):
        jurados = Jurado.objects.filter(avaliacoes__isnull=False).distinct().select_related("edicao")
        return [(jurado.pk, str(jurado)) for jurado in jurados]

    def queryset(self, request, queryset):
        return queryset.filter(jurado_id=self.value()) if self.value() else queryset


@admin.register(Avaliacao)
class AvaliacaoAdmin(admin.ModelAdmin):
    inlines = [NotaInline]
    list_display = ["jurado", "rotulo_projeto", "digitado_por", "digitado_em"]
    list_filter = [("jurado__edicao", admin.RelatedOnlyFieldListFilter), JuradoFiltro]
    list_select_related = ["jurado__edicao", "projeto", "digitado_por"]
    search_fields = ["projeto__titulo"]

    @admin.display(description="projeto", ordering="projeto_id")
    def rotulo_projeto(self, avaliacao):
        return f"#{avaliacao.projeto_id} — {avaliacao.projeto.titulo}"

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return []
        return ["jurado", "projeto", "digitado_por", "digitado_em", "alterado_por", "alterado_em"]

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is not None:
            return super().get_form(request, obj, change, **kwargs)
        jurado = _jurado_da_url(request)
        return _form_da_ficha(jurado) if jurado else EscolherJuradoForm

    def get_inline_instances(self, request, obj=None):
        if obj is None and _jurado_da_url(request) is None:
            return []
        return super().get_inline_instances(request, obj)

    def get_formset_kwargs(self, request, obj, inline, prefix):
        if obj.pk is None:
            # O admin monta os formsets antes de validar o formulário do pai:
            # o jurado do passo 2 já vai na instância (o campo dele é fixo).
            obj.jurado = _jurado_da_url(request)
        kwargs = super().get_formset_kwargs(request, obj, inline, prefix)
        if obj.pk is None:  # uma linha por critério, na ordem da ficha
            kwargs["initial"] = [{"criterio": c.pk} for c in _criterios_do(obj.jurado).order_by("ordem")]
        return kwargs

    def add_view(self, request, form_url="", extra_context=None):
        if "jurado" in request.GET and _jurado_da_url(request) is None:
            self.message_user(request, "Jurado inválido ou de edição sem votação aberta.", messages.WARNING)
            return HttpResponseRedirect(request.path)
        if _jurado_da_url(request) is None:
            if request.method == "POST":
                escolha = EscolherJuradoForm(request.POST)
                if escolha.is_valid():
                    url = self._com_jurado(request.get_full_path(), escolha.cleaned_data["jurado"])
                    return HttpResponseRedirect(url)
            extra_context = {
                **(extra_context or {}),
                "title": "Adicionar avaliação: escolha o jurado",
                "show_save_and_add_another": False,
                "show_save_and_continue": False,
            }
        return super().add_view(request, form_url, extra_context)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """Duplo clique em "Salvar": as duas requisições passam na validação e a
        segunda bate no índice único. A transação do admin já desfez tudo; valida
        de novo, e agora o formulário volta com a mensagem da duplicata."""
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except IntegrityError:
            if request.method != "POST":
                raise
            return super().changeform_view(request, object_id, form_url, extra_context)

    @staticmethod
    def _com_jurado(url, jurado):
        partes = urlsplit(url)
        consulta = QueryDict(partes.query, mutable=True)
        consulta["jurado"] = jurado.pk
        return urlunsplit(partes._replace(query=consulta.urlencode()))

    def save_model(self, request, obj, form, change):
        request._banca_conferida = _conferida(obj.jurado.edicao_id)
        if not change:
            obj.digitado_por = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        if change and (form.has_changed() or any(f.has_changed() for fs in formsets for f in fs.forms)):
            obj.alterado_por, obj.alterado_em = request.user, timezone.now()
            obj.save(update_fields=["alterado_por", "alterado_em"])
        self._avisar_conferencia(request, obj.jurado.edicao_id)

    def delete_model(self, request, obj):
        request._banca_conferida = _conferida(obj.jurado.edicao_id)
        super().delete_model(request, obj)
        self._avisar_conferencia(request, obj.jurado.edicao_id)

    def delete_queryset(self, request, queryset):
        conferidas = {e for e in queryset.values_list("jurado__edicao_id", flat=True) if _conferida(e)}
        super().delete_queryset(request, queryset)
        if any(not _conferida(e) for e in conferidas):
            self.message_user(request, CONFERENCIA_DESFEITA, messages.WARNING)

    def _avisar_conferencia(self, request, edicao_id):
        if getattr(request, "_banca_conferida", False) and not _conferida(edicao_id):
            self.message_user(request, CONFERENCIA_DESFEITA, messages.WARNING)
