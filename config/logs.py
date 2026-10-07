"""Filtro de log do link de edição do grupo (spec 02, guardrail 3).

O token do link de edição vai na URL: /grupo/editar/<token>/... (ADR-009).
O Django registra todo 4xx/5xx em django.request com o caminho
("Not Found: /grupo/editar/<token>/") e a falha de CSRF em
django.security.csrf — o token, que dá acesso de escrita ao projeto, iria
para o log da plataforma. "Sem log de acesso" (ADR-006) cobre o gunicorn e
o proxy, não o log da aplicação.

Aqui a linha continua (serve para depurar), mas com "<token>" no lugar do
segmento — na mensagem e no traceback — e sem o objeto request (cookies,
query string). Diferente das rotas do visitante (votacao/logs.py): lá a
linha some por causa do horário (P2); aqui o problema é só o segredo.

Vai nos mesmos lugares do filtro do visitante (ver LOGGING): no handler
console, para pegar tudo, e nos loggers, porque o handler de testes não
herda o filtro do handler.
"""

import logging
import posixpath
import re

PREFIXO = "/grupo/editar/"
MASCARA = "<token>"
# O caminho do log é o pedido como chegou: barra dupla, maiúsculas e "../"
# também caem no 404 e levam o token. A detecção usa o caminho normalizado; a
# troca no texto aceita barras repetidas e qualquer caixa.
_ROTA = re.compile(r"^/grupo/editar/([^/]+)", re.IGNORECASE)
_NO_TEXTO = re.compile(r"(/+grupo/+editar/+)[^/\s'\"]+", re.IGNORECASE)


def _normalizado(caminho):
    # Junta as barras depois do "/" inicial: normpath preserva "//" no começo.
    return posixpath.normpath(re.sub(r"/+", "/", "/" + caminho))


def _token(record):
    caminho = getattr(getattr(record, "request", None), "path_info", None)
    if not isinstance(caminho, str):
        return None
    achado = _ROTA.match(_normalizado(caminho))
    return achado.group(1) if achado else None


class FiltroTokenEdicao(logging.Filter):
    def filter(self, record):
        token = _token(record)
        if token is None:
            return True
        texto = record.getMessage()
        if record.exc_info and record.exc_info[0] is not None:
            texto += "\n" + logging.Formatter().formatException(record.exc_info)
        # Mesmo um "token" curto e inválido sai mascarado no caminho; fora do
        # caminho (mensagem da exceção), só troca um texto que pareça token,
        # para não desfigurar a linha trocando uma letra solta.
        texto = _NO_TEXTO.sub(lambda m: m.group(1) + MASCARA, texto)
        if len(token) >= 8:
            texto = texto.replace(token, MASCARA)
        record.msg = texto
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        del record.request
        return True
