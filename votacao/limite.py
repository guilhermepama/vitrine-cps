"""Rate limit da emissão em `/entrar` (spec 03, "Rate limit da emissão"; G7).

Duas camadas, no `caches["default"]` (DatabaseCache, compartilhado entre os
workers):
- por estação e bloco de 45 s do `timestamp` do QR: 20 emissões, expira em 150 s;
- por IP: 300 emissões em 10 min. A chave leva só o HMAC do IP
  (`chave_ip`, de `cadastro/seguranca.py`), nunca o IP em claro.

O valor guardado é `(contagem, expira_em)`: o `incr` do Django faz `get` +
`set` com o timeout padrão e empurraria a expiração a cada emissão (armadilha
A2). Com o prazo no valor, cada `set` regrava o tempo que falta, e o contador
do IP do Wi-Fi do evento zera 10 min depois da primeira emissão, não depois
da última. Quem chama trava a linha da `Edicao` antes (`/entrar`): é essa
trava que impede duas emissões simultâneas de lerem a mesma contagem.
"""

from django.core.cache import caches

from cadastro.seguranca import chave_ip, ip_do_cliente
from votacao import assinatura

LIMITE_ESTACAO = 20
EXPIRA_ESTACAO = 150  # tolerância do QR (90 s + 5 s) com folga
LIMITE_IP = 300
EXPIRA_IP = 10 * 60


def chave_estacao(estacao_id, ts):
    return f"rl:entrar:estacao:{estacao_id}:{ts // assinatura.ROTACAO_QR}"


def chave_do_ip(request):
    return "rl:entrar:ip:" + chave_ip(ip_do_cliente(request))


def _ler(cache, chave, momento):
    valor = cache.get(chave)
    if not isinstance(valor, tuple) or len(valor) != 2 or valor[1] <= momento:
        return None
    return valor


def _contar(cache, chave, validade, momento, valor):
    if valor is None:
        contagem, expira_em = 1, momento + validade
    else:
        contagem, expira_em = valor[0] + 1, valor[1]
    cache.set(chave, (contagem, expira_em), timeout=expira_em - momento)


def liberar(request, estacao_id, ts):
    """True se cabe nas duas camadas, e então conta a emissão nas duas.

    Recusada não conta: o QR repassado esgota a estação, mas não come o
    limite do IP do Wi-Fi que todos os visitantes dividem.
    """
    cache = caches["default"]
    momento = assinatura.agora()
    camadas = [
        (chave_estacao(estacao_id, ts), LIMITE_ESTACAO, EXPIRA_ESTACAO),
        (chave_do_ip(request), LIMITE_IP, EXPIRA_IP),
    ]
    lidos = [_ler(cache, chave, momento) for chave, _, _ in camadas]
    if any(valor is not None and valor[0] >= limite for valor, (_, limite, _) in zip(lidos, camadas)):
        return False
    for valor, (chave, _, validade) in zip(lidos, camadas):
        _contar(cache, chave, validade, momento, valor)
    return True
