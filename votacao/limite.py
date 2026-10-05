"""Rate limit da emissão em `/entrar` (spec 03, "Rate limit da emissão"; G7)
e do cadastro em `POST /visitantes` (decisão 4 do PR #33).

Contadores no `caches["default"]` (DatabaseCache, compartilhado entre os
workers):
- `/entrar`, por estação e bloco de 45 s do `timestamp` do QR: 20 emissões,
  expira em 150 s;
- `/entrar`, por IP: 300 emissões em 10 min;
- `POST /visitantes`, por IP e bloco fixo de 10 min: 300 envios.
As chaves de IP levam só o HMAC do IP (`chave_ip`, de
`cadastro/seguranca.py`), nunca o IP em claro.

O valor guardado é `(contagem, expira_em)`: o `incr` do Django faz `get` +
`set` com o timeout padrão e empurraria a expiração a cada emissão (armadilha
A2). Com o prazo no valor, cada `set` regrava o tempo que falta, e o contador
do IP do Wi-Fi do evento zera 10 min depois da primeira emissão, não depois
da última. Quem chama trava a linha da `Edicao` antes da contagem que vale:
é essa trava que impede dois envios simultâneos de lerem a mesma contagem.
As pré-leituras (`esgotado`, `cadastro_no_teto`) só leem, sem trava, para
recusar rápido quem já está no teto.

O contador do cadastro é por **bloco fixo** (decisão do coordenador no
PR #35): a chave termina no número do bloco e expira no fim dele. Com
"primeiro cadastro + 600 s", a coluna `expires` guardaria o horário do
cadastro com segundos, e o mesmo HMAC na chave do `/entrar` ligaria, num
`pg_dump`, o horário do token ao do cadastro (B1, ADR-003).
"""

from django.core.cache import caches

from cadastro.seguranca import chave_ip, ip_do_cliente
from votacao import assinatura

LIMITE_ESTACAO = 20
EXPIRA_ESTACAO = 150  # tolerância do QR (90 s + 5 s) com folga
LIMITE_IP = 300
EXPIRA_IP = 10 * 60
BLOCO_CADASTRO = 10 * 60


def chave_estacao(estacao_id, ts):
    return f"rl:entrar:estacao:{estacao_id}:{ts // assinatura.ROTACAO_QR}"


def chave_do_ip(request):
    return "rl:entrar:ip:" + chave_ip(ip_do_cliente(request))


def chave_do_ip_cadastro(request, momento=None):
    """Chave do bloco fixo de 10 min em que `momento` cai (padrão: agora)."""
    momento = assinatura.agora() if momento is None else momento
    return f"rl:visitantes:ip:{chave_ip(ip_do_cliente(request))}:{momento // BLOCO_CADASTRO}"


def fim_do_bloco_cadastro(momento):
    return (momento // BLOCO_CADASTRO + 1) * BLOCO_CADASTRO


def _ler(cache, chave, momento):
    valor = cache.get(chave)
    if not isinstance(valor, tuple) or len(valor) != 2 or valor[1] <= momento:
        return None
    return valor


def _contar(cache, chave, expira_se_novo, momento, valor):
    if valor is None:
        contagem, expira_em = 1, expira_se_novo
    else:
        contagem, expira_em = valor[0] + 1, valor[1]
    cache.set(chave, (contagem, expira_em), timeout=expira_em - momento)


# Camada = (chave, limite, expira_em de um contador novo).
def _camadas_entrar(request, estacao_id, ts, momento):
    return [
        (chave_estacao(estacao_id, ts), LIMITE_ESTACAO, momento + EXPIRA_ESTACAO),
        (chave_do_ip(request), LIMITE_IP, momento + EXPIRA_IP),
    ]


def _camadas_cadastro(request, momento):
    return [(chave_do_ip_cadastro(request, momento), LIMITE_IP, fim_do_bloco_cadastro(momento))]


def _algum_esgotado(lidos, camadas):
    return any(valor is not None and valor[0] >= limite for valor, (_, limite, _) in zip(lidos, camadas))


def _so_ler(montar):
    """True se alguma camada já está no limite. Só lê: não conta nem grava."""
    cache = caches["default"]
    momento = assinatura.agora()
    camadas = montar(momento)
    return _algum_esgotado([_ler(cache, chave, momento) for chave, _, _ in camadas], camadas)


def _liberar(montar):
    """Recusa sem contar se alguma camada está no limite; senão conta em todas."""
    cache = caches["default"]
    momento = assinatura.agora()
    camadas = montar(momento)
    lidos = [_ler(cache, chave, momento) for chave, _, _ in camadas]
    if _algum_esgotado(lidos, camadas):
        return False
    for valor, (chave, _, expira_se_novo) in zip(lidos, camadas):
        _contar(cache, chave, expira_se_novo, momento, valor)
    return True


def esgotado(request, estacao_id, ts):
    """Pré-leitura **sem** a trava da `Edicao` em `/entrar`, para recusar
    rápido quem já estourou (um script repetindo a URL não enfileira na
    frente dos `/votos`). Não substitui o `liberar`: entre esta leitura e a
    trava outra emissão pode contar, e quem decide é a contagem sob a trava.
    """
    return _so_ler(lambda momento: _camadas_entrar(request, estacao_id, ts, momento))


def liberar(request, estacao_id, ts):
    """True se cabe nas duas camadas, e então conta a emissão nas duas.

    Recusada não conta: o QR repassado esgota a estação, mas não come o
    limite do IP do Wi-Fi que todos os visitantes dividem.
    """
    return _liberar(lambda momento: _camadas_entrar(request, estacao_id, ts, momento))


def cadastro_no_teto(request):
    """Só lê, sem contar nem travar: True se o IP já chegou ao teto do cadastro."""
    return _so_ler(lambda momento: _camadas_cadastro(request, momento))


def liberar_cadastro(request):
    """True se o IP ainda cabe no limite do cadastro, e então conta o envio.

    Chamar com a linha da `Edicao` travada: é o que torna a contagem exata.
    """
    return _liberar(lambda momento: _camadas_cadastro(request, momento))
