"""Assinatura da janela do QR das estações (spec 03, "Emissão de token").

O QR aponta para `/entrar?w=<estacao>:<timestamp>&sig=<HMAC>`. O timestamp é
gerado pelo servidor na hora de desenhar o QR; `/entrar` aceita de agora − 90s
a agora + 5s (a janela atual e a anterior, com folga para o celular). O segredo
vem só do `settings` (G3) e nunca sai daqui: nem em template, nem em log.
"""

import hashlib
import hmac
import re
import time

from django.conf import settings

ROTACAO_QR = 45  # segundos entre um QR e o próximo
TOLERANCIA_PASSADO = 90
TOLERANCIA_FUTURO = 5

MAX_ESTACAO = 2147483647
MAX_W = 32
# Só dígitos ASCII ([0-9], não \d, que aceita outros alfabetos); sem sinal e
# sem zero à esquerda na estação; timestamp Unix em segundos com 10 dígitos.
_W = re.compile(r"([1-9][0-9]{0,9}):([1-9][0-9]{9})")
_SIG = re.compile(r"[0-9a-f]{64}")


def agora():
    return int(time.time())


def assinar(estacao_id, ts):
    """HMAC-SHA256 de `<estacao>:<timestamp>`, em hex minúsculo."""
    mensagem = f"{estacao_id}:{ts}".encode()
    return hmac.new(settings.QR_HMAC_SECRET.encode(), mensagem, hashlib.sha256).hexdigest()


def nova_janela(estacao_id):
    """Parâmetros `w` e `sig` do QR da estação, com o timestamp de agora."""
    ts = agora()
    return {"w": f"{estacao_id}:{ts}", "sig": assinar(estacao_id, ts)}


def _unico(query, nome):
    valores = query.getlist(nome)
    return valores[0].strip() if len(valores) == 1 else None


def ler_janela(query):
    """`(estacao_id, ts)` se `w` e `sig` da query são válidos e estão no prazo; senão None.

    `query` é o `request.GET` (QueryDict). Aplica a matriz de validação da
    spec antes de calcular qualquer HMAC, compara a assinatura em tempo
    constante (G2) e só então confere a janela. Quem chama não sabe qual
    regra barrou — a resposta tem de ser a mesma em todos os casos (G5).
    """
    w = _unico(query, "w")
    sig = _unico(query, "sig")
    if w is None or sig is None or len(w) > MAX_W:
        return None
    partes = _W.fullmatch(w)
    if partes is None or _SIG.fullmatch(sig) is None:
        return None
    estacao_id, ts = int(partes[1]), int(partes[2])
    if estacao_id > MAX_ESTACAO:
        return None
    if not hmac.compare_digest(assinar(estacao_id, ts), sig):
        return None
    momento = agora()
    if not momento - TOLERANCIA_PASSADO <= ts <= momento + TOLERANCIA_FUTURO:
        return None
    return estacao_id, ts
