"""Filtro de log P2 das rotas do visitante (spec 03, "Correlação visitante × token").

A plataforma carimba com segundos cada linha que a aplicação escreve; uma
linha por request em /entrar, /visitantes, /votar ou /votos bastaria para
ligar o cadastro ao token pelo horário. Por isso, nessas rotas, só o 5xx
gera linha — e reescrita, sem a mensagem da exceção (o IntegrityError traz
os valores da chave) e sem o objeto request (IP, cookies, query string).

Vai como filtro do LOGGER, não do handler: assertLogs troca os handlers e
um filtro de handler sumiria nos testes (armadilha A3 do plano). Filtro de
logger só vale para registros criados nele mesmo, não para os propagados
dos filhos — por isso `django.security.csrf` entra em LOGGING pelo nome.
"""

import logging
import traceback

ROTAS_VISITANTE = frozenset({"/entrar", "/visitantes", "/votar", "/votos"})


def _rota_visitante(record):
    caminho = getattr(getattr(record, "request", None), "path", None)
    if not isinstance(caminho, str):
        return None
    rota = caminho.rstrip("/")
    return rota if rota in ROTAS_VISITANTE else None


def _anonimizar_5xx(record, rota):
    exc_info = record.exc_info
    if exc_info and exc_info[0] is not None:
        # Só nome do tipo e arquivo:linha em função de cada quadro.
        # extract_tb não captura variáveis locais (capture_locals é False).
        tipo = exc_info[0].__name__
        quadros = [f"{q.filename}:{q.lineno} em {q.name}" for q in traceback.extract_tb(exc_info[2])]
    else:
        tipo, quadros = f"HTTP {record.status_code}", []
    record.msg = "\n  ".join([f"{tipo} em {rota}", *quadros])
    record.args = ()
    record.exc_info = None
    record.exc_text = None
    record.stack_info = None
    # status_code fica: é só o número (500), não identifica ninguém e é o que
    # separa erro de servidor de erro do cliente ao ler o log no evento.
    del record.request


class FiltroRotasVisitante(logging.Filter):
    def filter(self, record):
        rota = _rota_visitante(record)
        if rota is None:
            # Outras rotas, ou registro sem request (o código da votação não
            # passa dado do visitante ao logger — isso é revisão de código).
            return True
        if record.name.startswith("django.security"):
            return False  # CSRF e SuspiciousOperation: linha por request
        if (getattr(record, "status_code", None) or 0) >= 500:
            _anonimizar_5xx(record, rota)
            return True
        # 4xx e qualquer outra linha com request dessas rotas: P2 não
        # escreve linha por request.
        return False
