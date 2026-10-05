"""Cookie do token (spec 03, "Emissão de token" e "Validação de entrada").

Só `/entrar` grava; `/votar` e `/votos` leem. O cadastro não importa este
módulo (guardrail 6).
"""

import re

from votacao.models import Token

COOKIE_TOKEN = "token"
VALIDADE_COOKIE = 24 * 60 * 60  # 1 dia, como o cookie de cadastro
# UUID canônico: 36 caracteres, minúsculo, com hífens. Outro valor = sem cookie.
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def valor_bem_formado(request):
    """Valor do cookie se for UUID canônico; senão None. Não consulta o banco."""
    valor = request.COOKIES.get(COOKIE_TOKEN, "")
    return valor if _UUID.fullmatch(valor) else None


def token_do_cookie(request, edicao):
    """Token do cookie, se existe e é de estação da edição em votação; senão None.

    Cookie do ensaio, inexistente ou malformado é ignorado, sem apagar nem
    alterar o token antigo.
    """
    valor = valor_bem_formado(request)
    if valor is None:
        return None
    return Token.objects.filter(pk=valor, estacao__edicao=edicao).first()


def gravar_cookie(response, token):
    response.set_cookie(
        COOKIE_TOKEN,
        str(token.pk),
        max_age=VALIDADE_COOKIE,
        secure=True,
        httponly=True,
        samesite="Lax",
    )
