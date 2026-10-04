"""Cédula `GET /votar` e registro `POST /votos` (spec 03, "Cédula" e "Voto").

O voto confere tudo na mesma transação, com a linha da `Edicao` travada
(G4: antes ou depois do encerramento, nunca no meio); a unicidade de
(token, projeto) é da constraint do banco. Toda rejeição é o mesmo 409,
byte a byte (G5). Nenhum `logger` aqui (P2).
"""

import json
import re

from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from cadastro.models import Projeto
from votacao.cookie_token import token_do_cookie, valor_bem_formado
from votacao.liberacao import cadastro_valido
from votacao.models import Voto
from votacao.servicos import edicao_em_votacao

# TODO(#23): trocar por reverse("vitrine:como_votar") quando a spec 02 entrar.
# Caminho fixo da spec, sem rota provisória: a página é do app vitrine.
ROTA_COMO_VOTAR = "/como-votar/"

MAX_PROJETO = 2147483647
_PROJETO_ID = re.compile(r"[0-9]{1,10}")


def _json(dados):
    return json.dumps(dados, ensure_ascii=False).encode()


REGISTRADO = _json({"status": "registrado"})
INVALIDO = _json({"status": "invalido", "mensagem": "requisição inválida"})
REJEITADO = _json({"status": "rejeitado", "mensagem": "voto já registrado"})


def _resposta(corpo, status):
    return HttpResponse(corpo, status=status, content_type="application/json; charset=utf-8")


def _rejeitado():
    return _resposta(REJEITADO, 409)


# never_cache por fora: a cédula muda a cada voto e não fica no histórico.
@never_cache
@require_GET
def votar(request):
    if valor_bem_formado(request) is None:
        return HttpResponseRedirect(ROTA_COMO_VOTAR)
    edicao = edicao_em_votacao()
    if edicao is None:
        return render(request, "votacao/cedula.html", {"encerrada": True})
    token = token_do_cookie(request, edicao)
    if token is None:
        return HttpResponseRedirect(ROTA_COMO_VOTAR)
    if not cadastro_valido(request, edicao):
        return HttpResponseRedirect(reverse("votacao:visitantes"))
    projetos = (
        Projeto.objects.filter(status=Projeto.Status.PUBLICADO, turma__edicao=edicao)
        .select_related("turma__curso")
        .order_by("turma__curso__sigla", "turma__tipo_periodo", "turma__numero_periodo", "turma__pk", "titulo")
    )
    contexto = {
        "projetos": projetos,
        "votados": set(token.votos.values_list("projeto_id", flat=True)),
    }
    return render(request, "votacao/cedula.html", contexto)


def _projeto_id(request):
    """`projeto_id` válido pela matriz da spec, ou None. Não consulta o banco (G12)."""
    valores = request.POST.getlist("projeto_id")
    if len(valores) != 1:
        return None
    texto = valores[0].strip(" ")
    if not _PROJETO_ID.fullmatch(texto) or not 1 <= int(texto) <= MAX_PROJETO:
        return None
    return int(texto)


@never_cache
@require_POST
def votos(request):
    projeto_id = _projeto_id(request)
    if projeto_id is None:
        return _resposta(INVALIDO, 400)
    with transaction.atomic():
        edicao = edicao_em_votacao(travar=True)
        if edicao is None:
            return _rejeitado()
        token = token_do_cookie(request, edicao)
        if token is None or not cadastro_valido(request, edicao):
            return _rejeitado()
        publicado = Projeto.objects.filter(pk=projeto_id, status=Projeto.Status.PUBLICADO, turma__edicao=edicao)
        if not publicado.exists():
            return _rejeitado()
        try:
            # Savepoint: o IntegrityError não estraga a transação de fora.
            with transaction.atomic():
                Voto.objects.create(token=token, projeto_id=projeto_id)
        except IntegrityError:
            return _rejeitado()
    return _resposta(REGISTRADO, 201)
