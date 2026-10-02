"""RA e link de edição (ADR-009, spec 01).

O RA em claro nunca é gravado, logado nem exibido: só o HMAC-SHA256 com
RA_HMAC_SECRET. O token de edição é aleatório; só o SHA-256 vai para o banco.
"""

import hashlib
import hmac
import secrets

from django.conf import settings


def normalizar_ra(ra):
    """Mantém só os dígitos (zeros à esquerda preservados)."""
    digitos = "".join(c for c in str(ra) if c.isdigit())
    if not digitos:
        raise ValueError("RA sem dígitos.")
    return digitos


def hash_ra(ra):
    chave = settings.RA_HMAC_SECRET.encode()
    return hmac.new(chave, normalizar_ra(ra).encode(), hashlib.sha256).hexdigest()


def ra_confere(ra, ra_hmac):
    try:
        calculado = hash_ra(ra)
    except ValueError:
        return False
    return hmac.compare_digest(calculado, ra_hmac or "")


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def gerar_token_edicao():
    """Devolve (token em claro, hash). O token em claro é mostrado uma vez e descartado."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def token_confere(token, token_hash):
    if not token or not token_hash:
        return False
    return hmac.compare_digest(hash_token(token), token_hash)
