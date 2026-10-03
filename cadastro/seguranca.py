"""RA e link de edição (ADR-009, spec 01); IP do cliente para rate limit (specs 02 e 03).

O RA em claro nunca é gravado, logado nem exibido: só o HMAC-SHA256 com
RA_HMAC_SECRET. O token de edição é aleatório; só o SHA-256 vai para o banco.
O IP em claro só existe em memória durante a requisição: a chave de cache é
o HMAC-SHA256 com IP_HMAC_SECRET.
"""

import hashlib
import hmac
import ipaddress
import re
import secrets

from django.conf import settings


_SEPARADORES = str.maketrans("", "", " .-/")


def normalizar_ra(ra):
    """Remove espaço, ponto, hífen e barra; o resto tem de ser 5 a 20 dígitos.

    Qualquer outro caractere é recusado, não descartado: um RA "limpo" em
    silêncio geraria um hash que não confere com o do representante.
    """
    texto = str(ra).strip().translate(_SEPARADORES)
    if not re.fullmatch(r"[0-9]{5,20}", texto):
        raise ValueError("RA inválido.")
    return texto


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


# --- IP do cliente (rate limit das specs 02 e 03) ----------------------------

# Chave usada quando o IP não chega ou não é um IP válido. Todas essas
# requisições dividem um único contador: o limite fica mais apertado para
# elas, nunca mais frouxo.
_IP_DESCONHECIDO = "desconhecido"


def ip_do_cliente(request):
    """Texto do IP do cliente, como chegou. Nunca logar nem gravar o retorno.

    Com `settings.IP_HEADER` vazio (desenvolvimento, CI), usa REMOTE_ADDR.
    Em produção, o cabeçalho é o que o proxy da hospedagem garante (ADR-006).
    Se ele vier como lista (X-Forwarded-For), vale o **último** item — o que
    o nosso proxy acrescentou; os anteriores vêm do cliente e podem ser falsos.
    """
    if not settings.IP_HEADER:
        return request.META.get("REMOTE_ADDR", "")
    chave_meta = "HTTP_" + settings.IP_HEADER.upper().replace("-", "_")
    valor = request.META.get(chave_meta, "")
    return valor.rsplit(",", 1)[-1].strip()


def _normalizar_ip(texto):
    """IPv4 como está; IPv6 reduzido ao prefixo /64; inválido vira chave fixa.

    Cada aparelho em IPv6 recebe um /64 inteiro e pode trocar o endereço à
    vontade dentro dele: contar por endereço furaria o limite.
    """
    try:
        ip = ipaddress.ip_address((texto or "").strip())
    except ValueError:
        return _IP_DESCONHECIDO
    if ip.version == 6:
        if ip.ipv4_mapped:
            return str(ip.ipv4_mapped)
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


def chave_ip(texto_ip):
    """HMAC-SHA256 (hex) do IP normalizado — é isto que vai na chave do cache.

    Cada app põe o seu prefixo na frente (ex.: "rl:entrar:ip:<chave>").
    """
    chave = settings.IP_HMAC_SECRET.encode()
    return hmac.new(chave, _normalizar_ip(texto_ip).encode(), hashlib.sha256).hexdigest()
