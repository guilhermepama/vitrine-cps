"""Emissão do token em `GET /entrar` (spec 03, "Emissão de token" e "Rate limit
da emissão").

Ordem da spec: validação de entrada → assinatura e janela → pré-leitura do
rate limit sem trava → transação com a trava da `Edicao` → rate limit →
estação → token. Toda recusa é a mesma
página "QR expirado" (400, corpo idêntico ao do /visitantes) e nenhuma cria
token. Nenhum `logger` aqui (P2).
"""

import re

from django.db import transaction
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from votacao.assinatura import ler_janela
from votacao.liberacao import cadastro_valido
from votacao.limite import esgotado, liberar
from votacao.models import Estacao, Token
from votacao.respostas import qr_expirado
from votacao.servicos import edicao_em_votacao
from votacao.views_visitante import ROTA_CEDULA

COOKIE_TOKEN = "token"
VALIDADE_COOKIE = 24 * 60 * 60  # 1 dia, como o cookie de cadastro
# UUID canônico: 36 caracteres, minúsculo, com hífens. Outro valor = sem cookie.
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _token_do_cookie(request, edicao):
    """Token do cookie, se existe e é de estação da edição em votação; senão None.

    Cookie do ensaio, inexistente ou malformado é ignorado, sem apagar nem
    alterar o token antigo.
    """
    valor = request.COOKIES.get(COOKIE_TOKEN, "")
    if not _UUID.fullmatch(valor):
        return None
    return Token.objects.filter(pk=valor, estacao__edicao=edicao).first()


# never_cache por fora: o token não fica em cache de navegador nem de proxy.
@never_cache
@require_GET
def entrar(request):
    janela = ler_janela(request.GET)
    if janela is None:
        return qr_expirado()
    estacao_id, ts = janela
    # Já estourado: recusa sem esperar a trava (não enfileira na frente dos
    # /votos). Só lê; a decisão que conta é a de `liberar`, sob a trava.
    if esgotado(request, estacao_id, ts):
        return qr_expirado()
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
        token = _token_do_cookie(request, edicao) or Token.objects.create(estacao=estacao)
    destino = ROTA_CEDULA if cadastro_valido(request, edicao) else reverse("votacao:visitantes")
    resposta = render(request, "votacao/entrar.html", {"token": str(token.pk), "destino": destino})
    resposta.set_cookie(
        COOKIE_TOKEN,
        str(token.pk),
        max_age=VALIDADE_COOKIE,
        secure=True,
        httponly=True,
        samesite="Lax",
    )
    return resposta
