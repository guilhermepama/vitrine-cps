"""Admin do cadastro: edições, cursos, turmas, projetos e moderação (spec 01, 3/3).

Tudo aqui é só para superusuário nesta edição (G15). Os campos travados
(`status`, `slug`, pesos depois de abrir a votação) mudam só pelos métodos do
model — as ações abaixo chamam `publicar()`, `devolver_para_ajustes()`,
`regerar_link()` e `revogar_link()`, nunca `QuerySet.update()`.

O RA em claro nunca é exibido nem gravado: o campo "RA do representante" é só
de escrita e vira `ra_hmac` no `clean`. `ra_hmac` e `token_edicao_hash` ficam
fora dos formulários (`editable=False`).
"""

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import NoReverseMatch, reverse

from cadastro.models import Curso, Edicao, ImagemProjeto, Integrante, Projeto, Turma
from cadastro.seguranca import hash_ra

MOTIVO_FOTOS_ETEC = (
    "Retire as fotos em que aparecem pessoas (regra da Etec para menores de idade)"
)


class SoSuperusuarioMixin:
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request, *args):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


# --- Edição ---------------------------------------------------------------------


class EdicaoForm(forms.ModelForm):
    class Meta:
        model = Edicao
        fields = ["nome", "data_evento", "ativa", "prazo_edicao", "peso_banca", "peso_publico"]

    def clean(self):
        dados = super().clean()
        # A constraint do banco já recusa; aqui a mensagem é legível em vez de erro 500.
        if dados.get("ativa"):
            outra = Edicao.objects.filter(ativa=True).exclude(pk=self.instance.pk).first()
            if outra:
                raise ValidationError(f"A edição {outra} está ativa. Desative-a antes de ativar outra.")
        return dados


@admin.register(Edicao)
class EdicaoAdmin(SoSuperusuarioMixin, admin.ModelAdmin):
    form = EdicaoForm
    list_display = ["nome", "ativa", "data_evento", "prazo_edicao", "votacao_aberta_em"]
    list_filter = ["ativa"]
    # Preenchidos pela votação (spec 03) e pela conferência da banca (spec 06).
    readonly_fields = ["votacao_aberta_em", "votacao_encerrada_em", "banca_conferida_em"]

    def get_readonly_fields(self, request, obj=None):
        campos = list(super().get_readonly_fields(request, obj))
        if obj is not None and obj.votacao_aberta_em is not None:
            campos += ["peso_banca", "peso_publico"]  # ADR-007: não mudam depois de abrir
        return campos


# --- Curso e turma --------------------------------------------------------------


@admin.register(Curso)
class CursoAdmin(SoSuperusuarioMixin, admin.ModelAdmin):
    list_display = ["sigla", "nome", "unidade", "ativo"]
    list_filter = ["unidade", "ativo"]
    search_fields = ["sigla", "nome"]


@admin.register(Turma)
class TurmaAdmin(SoSuperusuarioMixin, admin.ModelAdmin):
    list_display = ["rotulo", "edicao"]
    list_filter = ["edicao", "curso"]
    list_select_related = ["edicao", "curso"]

    @admin.display(description="turma")
    def rotulo(self, turma):
        return turma.rotulo


# --- Projeto --------------------------------------------------------------------


class LimiteNoFormsetMixin:
    """Recusa (não só esconde) o formulário acima do máximo: `validate_max`."""

    def get_formset(self, request, obj=None, **kwargs):
        kwargs.setdefault("validate_max", True)
        return super().get_formset(request, obj, **kwargs)


class IntegranteInline(SoSuperusuarioMixin, LimiteNoFormsetMixin, admin.TabularInline):
    model = Integrante
    fields = ["nome", "papel", "ordem"]
    extra = 0
    max_num = Integrante.MAXIMO_POR_PROJETO


class ImagemInline(SoSuperusuarioMixin, LimiteNoFormsetMixin, admin.TabularInline):
    model = ImagemProjeto
    fields = ["arquivo", "legenda", "ordem"]
    extra = 0
    max_num = ImagemProjeto.MAXIMO_POR_PROJETO


def _campo_https(campo, **kwargs):
    if isinstance(campo, models.URLField):
        kwargs["assume_scheme"] = "https"
    return campo.formfield(**kwargs)


class ProjetoForm(forms.ModelForm):
    # Só de escrita: PasswordInput(render_value=False) nunca devolve o valor ao HTML,
    # nem ao reabrir, nem depois de um erro de validação (G11).
    ra_representante = forms.CharField(
        label="RA do representante",
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "off"}),
        help_text="Obrigatório na criação. Na edição, deixe vazio para manter o atual. Nunca é exibido.",
    )

    class Meta:
        model = Projeto
        formfield_callback = _campo_https
        fields = [
            "turma",
            "titulo",
            "representante_nome",
            "ra_representante",
            "resumo",
            "descricao",
            "componente_origem",
            "capa",
            "link_repositorio",
            "link_demo",
            "link_video",
            "motivo_ajustes",
        ]
        help_texts = {
            "motivo_ajustes": (
                "Mostrado ao grupo ao devolver para ajustes. Projeto da Etec com foto de pessoa: "
                f"“{MOTIVO_FOTOS_ETEC}”."
            ),
        }

    def clean_ra_representante(self):
        ra = self.cleaned_data.get("ra_representante", "")
        if not ra:
            if not self.instance.pk:
                raise ValidationError("Informe o RA do representante.")
            return ""
        try:
            # Antes do full_clean do model, que confere o RA único na edição.
            self.instance.ra_hmac = hash_ra(ra)
        except ValueError:
            raise ValidationError("RA inválido: use só números (5 a 20 dígitos).") from None
        return ""  # nada do RA em claro fica no cleaned_data


def _link_de_edicao(token):
    """URL_PUBLICA + rota do grupo (spec 02). Nunca o Host da requisição."""
    try:
        caminho = reverse("vitrine:editar", args=[token])
    except NoReverseMatch:  # rota da spec 02 ainda não entrou
        caminho = f"/grupo/editar/{token}/"
    return f"{settings.URL_PUBLICA}{caminho}"


@admin.register(Projeto)
class ProjetoAdmin(SoSuperusuarioMixin, admin.ModelAdmin):
    form = ProjetoForm
    formfield_overrides = {models.URLField: {"assume_scheme": "https"}}  # links só https
    inlines = [IntegranteInline, ImagemInline]
    list_display = ["titulo", "turma", "status", "reivindicado", "atualizado_em"]
    list_filter = ["status", "turma__edicao", "turma__curso"]
    list_select_related = ["turma__curso", "turma__edicao"]
    search_fields = ["titulo", "representante_nome"]
    readonly_fields = ["status", "slug", "publicado_em", "reivindicado_em", "link_ativo"]
    actions = ["acao_publicar", "acao_devolver", "acao_regerar_link", "acao_revogar_link"]

    def get_actions(self, request):
        # Sem "apagar selecionados": a exclusão em lote não passa pela trava abaixo.
        acoes = super().get_actions(request)
        acoes.pop("delete_selected", None)
        return acoes

    def has_delete_permission(self, request, obj=None):
        # Votação aberta: apagar tiraria o projeto da cédula (não há retirada nesta edição).
        if obj is not None and obj.turma.edicao.votacao_aberta_em is not None:
            return False
        return super().has_delete_permission(request, obj)

    @admin.display(description="reivindicado", boolean=True)
    def reivindicado(self, projeto):
        return projeto.reivindicado_em is not None

    @admin.display(description="link de edição")
    def link_ativo(self, projeto):
        if not projeto.token_edicao_hash:
            return "nenhum (regere pela ação da lista)"
        return f"ativo, gerado em {projeto.token_edicao_gerado_em:%d/%m/%Y %H:%M}"

    # Moderação em lote ------------------------------------------------------

    @admin.action(description="Publicar")
    def acao_publicar(self, request, queryset):
        publicados, de_fora = 0, []
        for projeto in queryset.select_related("turma"):
            try:
                pendencias = projeto.publicar()
            except ValidationError:
                de_fora.append(f"{projeto} (votação da edição já aberta)")
                continue
            if pendencias:
                de_fora.append(f"{projeto} (falta: {', '.join(pendencias)})")
            else:
                publicados += 1
                self.log_change(request, projeto, "Publicado")
        self._resumo(request, f"{publicados} projeto(s) publicado(s).", de_fora)

    @admin.action(description="Devolver para ajustes")
    def acao_devolver(self, request, queryset):
        devolvidos, de_fora = 0, []
        for projeto in queryset.select_related("turma"):
            try:
                devolveu = projeto.devolver_para_ajustes()
            except ValidationError:
                de_fora.append(f"{projeto} (votação da edição já aberta)")
                continue
            if devolveu:
                devolvidos += 1
                self.log_change(request, projeto, f"Devolvido para ajustes: {projeto.motivo_ajustes}")
            elif projeto.status not in (Projeto.Status.EM_REVISAO, Projeto.Status.PUBLICADO):
                de_fora.append(f"{projeto} (status {projeto.get_status_display()})")
            else:
                de_fora.append(f"{projeto} (sem motivo dos ajustes)")
        self._resumo(request, f"{devolvidos} projeto(s) devolvido(s) para ajustes.", de_fora)

    def _resumo(self, request, feito, de_fora):
        self.message_user(request, feito, messages.SUCCESS)
        if de_fora:
            self.message_user(request, "Ficaram como estavam: " + "; ".join(de_fora) + ".", messages.WARNING)

    # Link de edição (ADR-009) -------------------------------------------------

    @admin.action(description="Regerar link de edição (um projeto)")
    def acao_regerar_link(self, request, queryset):
        projetos = list(queryset[:2])
        if len(projetos) != 1:
            self.message_user(request, "Selecione exatamente um projeto para regerar o link.", messages.ERROR)
            return
        projeto = projetos[0]
        token = projeto.regerar_link()
        self.log_change(request, projeto, "Link de edição regerado")  # nunca o token
        # Mostrado uma vez: o token em claro não é gravado em lugar nenhum.
        self.message_user(
            request,
            f"Novo link de edição de “{projeto}” (o anterior deixou de valer). "
            f"Copie agora, ele não aparece de novo: {_link_de_edicao(token)}",
            messages.SUCCESS,
        )

    @admin.action(description="Revogar link de edição (um projeto)")
    def acao_revogar_link(self, request, queryset):
        # Um por vez: revogar em lote derrubaria o link de todos os grupos num clique.
        projetos = list(queryset[:2])
        if len(projetos) != 1:
            self.message_user(request, "Selecione exatamente um projeto para revogar o link.", messages.ERROR)
            return
        projeto = projetos[0]
        projeto.revogar_link()
        self.log_change(request, projeto, "Link de edição revogado")
        self.message_user(request, f"Link de edição de “{projeto}” revogado.", messages.SUCCESS)
