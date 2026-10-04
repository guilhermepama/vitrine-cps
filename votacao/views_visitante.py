"""Cadastro do visitante (spec 03, "Formulário de visitante" e "Cadastro do
visitante").

O cadastro não lê o cookie do token, o localStorage nem a estação: o único
cookie lido é o de cadastro, e a edição vem sempre da `Edicao` em votação
(guardrail 6, ADR-003). Nenhum `logger` aqui — linha de log com horário
ligaria o cadastro ao token (P2).
"""

from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from votacao.forms import VisitanteForm
from votacao.liberacao import cadastro_valido, gravar_cookie
from votacao.models import Visitante, truncar_para_hora
from votacao.respostas import qr_expirado
from votacao.servicos import edicao_em_votacao

# TODO(F6): trocar por reverse("votacao:votar") quando a cédula existir.
# Caminho fixo da spec, sem rota provisória: um /votar de mentira na main
# responderia sem as regras da cédula (guardrail 8).
ROTA_CEDULA = "/votar"

MENSAGEM_INVALIDO = "Não foi possível concluir o cadastro. Confira os campos."


def _formulario(request, form, status=200, mensagem=None):
    return render(request, "votacao/visitante.html", {"form": form, "mensagem": mensagem}, status=status)


# never_cache: sem cópia do formulário no histórico; o "voltar" refaz o GET,
# que leva à cédula quem já se cadastrou.
@never_cache
@require_http_methods(["GET", "POST"])
def visitantes(request):
    if request.method == "POST":
        return _cadastrar(request)
    edicao = edicao_em_votacao()
    if edicao is None:
        return qr_expirado()
    if cadastro_valido(request, edicao):
        return HttpResponseRedirect(ROTA_CEDULA)
    return _formulario(request, VisitanteForm())


def _cadastrar(request):
    # Validação antes de qualquer consulta (guardrail 12).
    form = VisitanteForm(request.POST)
    if not form.is_valid():
        return _formulario(request, form, status=400, mensagem=MENSAGEM_INVALIDO)
    dados = form.cleaned_data
    with transaction.atomic():
        edicao = edicao_em_votacao(travar=True)
        if edicao is None:
            return qr_expirado()
        # Já cadastrado nesta edição (aba antiga, reenvio): cédula, sem novo
        # registro — a mesma regra do GET (decisão 3 do PR #33).
        if cadastro_valido(request, edicao):
            return HttpResponseRedirect(ROTA_CEDULA)
        Visitante.objects.create(
            nome=dados["nome"],
            email=dados["email"],
            telefone=dados["telefone"],
            # Hora cheia no fuso do projeto (America/Sao_Paulo), gravada em UTC.
            consentimento_em=truncar_para_hora(timezone.localtime(timezone.now())),
            edicao=edicao,
        )
    resposta = HttpResponseRedirect(ROTA_CEDULA)
    gravar_cookie(resposta, edicao)
    return resposta
