"""Emissão do token em `GET /entrar` (spec 03, "Emissão de token" e "Rate limit
da emissão").

Ordem da spec: validação de entrada → assinatura e janela → transação com a
trava da `Edicao` → rate limit → estação → token. Toda recusa é a mesma
página "QR expirado" (400, corpo idêntico ao do /visitantes) e nenhuma cria
token. Nenhum `logger` aqui (P2).
"""

from django.db import transaction
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from votacao.assinatura import ler_janela
from votacao.cookie_token import gravar_cookie, token_do_cookie
from votacao.liberacao import cadastro_valido
from votacao.limite import liberar
from votacao.models import Estacao, Token
from votacao.respostas import qr_expirado
from votacao.servicos import edicao_em_votacao
from votacao.views_visitante import ROTA_CEDULA


# never_cache por fora: o token não fica em cache de navegador nem de proxy.
@never_cache
@require_GET
def entrar(request):
    janela = ler_janela(request.GET)
    if janela is None:
        return qr_expirado()
    estacao_id, ts = janela
    with transaction.atomic():
        # Edição travada antes de ler a estação (corrida A8 e referência temporal).
        edicao = edicao_em_votacao(travar=True)
        if edicao is None:
            return qr_expirado()
        # Contadores lidos e gravados com a linha da edição travada: as emissões
        # simultâneas se enfileiram e nenhuma escapa do limite (G7).
        if not liberar(request, estacao_id, ts):
            return qr_expirado()
        estacao = Estacao.objects.filter(pk=estacao_id, ativa=True, edicao=edicao).first()
        if estacao is None:
            return qr_expirado()
        token = token_do_cookie(request, edicao) or Token.objects.create(estacao=estacao)
    destino = ROTA_CEDULA if cadastro_valido(request, edicao) else reverse("votacao:visitantes")
    resposta = render(request, "votacao/entrar.html", {"token": str(token.pk), "destino": destino})
    gravar_cookie(resposta, token)
    return resposta
