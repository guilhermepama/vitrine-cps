"""Cookie de cadastro: libera a cédula sem ligar visitante e token (spec 03,
"Liberação da cédula").

O valor é só o id da edição em votação, assinado com `Signer` sem timestamp:
igual para todos os visitantes da edição, sem id de visitante, token, horário
ou número aleatório. Nada disso vai para sessão, cache ou tabela.
"""

from django.core.signing import BadSignature, Signer

COOKIE_CADASTRO = "cadastro"
VALIDADE_COOKIE = 24 * 60 * 60  # 1 dia


def _assinador():
    # Criado a cada chamada: lê SECRET_KEY e SECRET_KEY_FALLBACKS da hora.
    return Signer(salt="votacao.cadastro")


def valor_do_cookie(edicao):
    return _assinador().sign(str(edicao.pk))


def cadastro_valido(request, edicao):
    """Assinatura correta e edição igual à em votação. Qualquer outro caso
    (ausente, adulterado, de outra edição) é "sem cadastro"."""
    valor = request.COOKIES.get(COOKIE_CADASTRO)
    if edicao is None or not valor:
        return False
    try:
        return _assinador().unsign(valor) == str(edicao.pk)
    except BadSignature:
        return False


def gravar_cookie(response, edicao):
    response.set_cookie(
        COOKIE_CADASTRO,
        valor_do_cookie(edicao),
        max_age=VALIDADE_COOKIE,
        secure=True,
        httponly=True,
        samesite="Lax",
    )
