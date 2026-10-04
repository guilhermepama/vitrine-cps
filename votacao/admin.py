"""Admin da votação: abrir/encerrar e estações (spec 03).

Tudo aqui é só para superusuário (G15). Staff sem superusuário (ex: grupo
`digitacao-banca`, spec 06) não vê o menu e recebe 403 pela URL, mesmo que
tenha as permissões do model; anônimo vai para o login do admin.
"""

from django.contrib import admin, messages

from votacao import servicos
from votacao.models import EdicaoVotacao, Estacao


class SoSuperusuarioMixin:
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(EdicaoVotacao)
class EdicaoVotacaoAdmin(SoSuperusuarioMixin, admin.ModelAdmin):
    list_display = ["nome", "data_evento", "situacao", "votacao_aberta_em", "votacao_encerrada_em"]
    fields = ["nome", "data_evento", "votacao_aberta_em", "votacao_encerrada_em"]
    readonly_fields = fields
    actions = ["acao_abrir", "acao_encerrar"]

    # Somente leitura: a edição em si é do admin do cadastro; aqui só as ações.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_votacao_permission(self, request):
        return request.user.is_superuser

    def get_actions(self, request):
        # Tira a ação padrão de apagar; as demais exigem a permissão "votacao".
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    @admin.display(description="situação")
    def situacao(self, edicao):
        if edicao.votacao_encerrada_em:
            return "encerrada"
        if edicao.votacao_aberta_em:
            return "em votação"
        return "não aberta"

    @admin.action(description="Abrir votação", permissions=["votacao"])
    def acao_abrir(self, request, queryset):
        self._executar(request, queryset, servicos.abrir_votacao, "Votação aberta")

    @admin.action(description="Encerrar votação", permissions=["votacao"])
    def acao_encerrar(self, request, queryset):
        self._executar(request, queryset, servicos.encerrar_votacao, "Votação encerrada")

    def _executar(self, request, queryset, servico, sucesso):
        edicoes = list(queryset[:2])
        if len(edicoes) != 1:
            self.message_user(request, "Selecione exatamente uma edição.", messages.ERROR)
            return
        edicao = edicoes[0]
        recusa = servico(edicao.pk)
        if recusa:
            self.message_user(request, recusa, messages.ERROR)
            return
        self.log_change(request, edicao, sucesso)
        self.message_user(request, f"{sucesso}: {edicao}.", messages.SUCCESS)


@admin.register(Estacao)
class EstacaoAdmin(SoSuperusuarioMixin, admin.ModelAdmin):
    # Estação com token não muda de edição (ValidationError do model, vira erro
    # no formulário) nem é apagada (PROTECT: o admin lista o que impede).
    list_display = ["nome", "edicao", "ativa"]
    list_editable = ["ativa"]
    list_filter = ["edicao", "ativa"]
    search_fields = ["nome"]
    fields = ["nome", "edicao", "ativa"]
