"""Conferência da banca (spec 06, fatia 5).

Rota do `JuradoAdmin.get_urls()`, envolvida em `admin_site.admin_view`
(anônimo ou não staff → login do admin; `never_cache`; CSRF). Staff sem
`banca.concluir_conferencia` → 403; edição inexistente → 404.

GET: cobertura por jurado e por turma e a amostra a conferir (ou, com
`?digitador=<id>`, todas as avaliações daquele digitador). Número fixo de
consultas, independente do tamanho da edição.

POST (`acao`): "concluir" preenche `banca_conferida_em`; "reabrir" (decisão
do coordenador em 05/10, parecer do #55) apaga, e o passo 1 da digitação
volta a listar os jurados da edição. As duas com a `Edicao` travada e
registro no histórico do admin; recusa → 302 com a mensagem, nada muda.
"""

import hashlib
import random
from collections import Counter, defaultdict

from django.contrib import admin, messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from banca.fichas import ORDEM_TURMA, exige_permissao
from banca.models import Avaliacao, Criterio, Jurado, Nota
from cadastro.models import Edicao, Projeto, Turma

CONCLUIR_CONFERENCIA = "banca.concluir_conferencia"
AMOSTRA_MINIMA = 10

QUEM_DIGITOU = "Quem digitou fichas desta edição não pode concluir a conferência."
JA_CONFERIDA = "A conferência desta edição já foi concluída."
NAO_ENCERRADA = "A votação desta edição ainda não foi encerrada."
SEM_AVALIACOES = "Nenhuma avaliação digitada nesta edição."
NAO_CONFERIDA = "A conferência desta edição não está concluída; não há digitação a reabrir."


def tamanho_da_amostra(total):
    """20% arredondado para cima, no mínimo 10 (ou todas, se houver menos)."""
    return min(total, max(AMOSTRA_MINIMA, -(-total // 5)))


def sortear_amostra(edicao_id, ids):
    """Mesma amostra em qualquer processo, até mudar o conjunto de avaliações:
    a semente é o sha256 de `edicao_id` e dos ids em ordem (nada de `hash()`)."""
    ids = sorted(ids)
    semente = hashlib.sha256(f"{edicao_id}:{','.join(map(str, ids))}".encode()).digest()
    return random.Random(semente).sample(ids, tamanho_da_amostra(len(ids)))


def _url(edicao_id):
    return reverse("admin:banca_jurado_conferencia", args=[edicao_id])


@require_http_methods(["GET", "POST"])
@exige_permissao(CONCLUIR_CONFERENCIA)
def conferencia(request, id):
    if request.method == "POST":
        return _executar(request, id)
    edicao = get_object_or_404(Edicao, pk=id)
    digitador = request.GET.get("digitador")
    if digitador is not None and not (digitador.isascii() and digitador.isdigit()):
        messages.error(request, "Digitador inválido.")
        return redirect(_url(edicao.pk))
    return render(request, "banca/conferencia.html", _contexto(request, edicao, digitador and int(digitador)))


def _contexto(request, edicao, digitador):
    turmas = list(Turma.objects.filter(edicao=edicao).select_related("curso").order_by(*ORDEM_TURMA))
    jurados = list(Jurado.objects.filter(edicao=edicao).order_by("nome"))
    pares = Jurado.turmas.through.objects.filter(jurado__edicao=edicao, turma__edicao=edicao)
    jurados_da_turma, turmas_do_jurado = defaultdict(set), defaultdict(set)
    for jurado_id, turma_id in pares.values_list("jurado_id", "turma_id"):
        jurados_da_turma[turma_id].add(jurado_id)
        turmas_do_jurado[jurado_id].add(turma_id)
    publicados = defaultdict(list)
    for projeto in (
        Projeto.objects.filter(turma__edicao=edicao, status=Projeto.Status.PUBLICADO)
        .only("id", "titulo", "turma_id")
        .order_by("titulo", "id")
    ):
        publicados[projeto.turma_id].append(projeto)
    avaliacoes = list(
        Avaliacao.objects.filter(jurado__edicao=edicao).values_list(
            "id", "jurado_id", "projeto_id", "digitado_por_id", "digitado_por__username"
        )
    )
    por_jurado = Counter(a[1] for a in avaliacoes)
    por_projeto = Counter(a[2] for a in avaliacoes)
    digitadores = Counter((a[3], a[4]) for a in avaliacoes)

    cobertura_turmas = []
    for turma in turmas:
        n_jurados = len(jurados_da_turma[turma.pk])
        projetos = publicados[turma.pk]
        cobertura_turmas.append(
            {
                "turma": turma,
                "jurados": n_jurados,
                "publicados": len(projetos),
                "sem_avaliacao": [p for p in projetos if not por_projeto[p.pk]],
                "incompletos": [(p, por_projeto[p.pk]) for p in projetos if 0 < por_projeto[p.pk] < n_jurados],
            }
        )
    cobertura_jurados = [
        (jurado, por_jurado[jurado.pk], sum(len(publicados[t]) for t in turmas_do_jurado[jurado.pk]))
        for jurado in jurados
    ]

    if digitador is None:
        ids = sortear_amostra(edicao.pk, [a[0] for a in avaliacoes])
    else:
        ids = [a[0] for a in avaliacoes if a[3] == digitador]
    criterios = list(Criterio.objects.filter(edicao=edicao).order_by("ordem"))
    linhas = []
    notas = Prefetch("notas", queryset=Nota.objects.only("avaliacao_id", "criterio_id", "valor"))
    for avaliacao in (
        Avaliacao.objects.filter(pk__in=ids)
        .select_related("jurado", "projeto", "digitado_por")
        .prefetch_related(notas)
        .order_by("jurado__nome", "projeto_id")
    ):
        valores = {nota.criterio_id: nota.valor for nota in avaliacao.notas.all()}
        linhas.append((avaliacao, [valores.get(c.pk) for c in criterios]))

    return {
        **admin.site.each_context(request),
        "title": f"Conferência da banca — {edicao.nome}",
        "edicao": edicao,
        "criterios": criterios,
        "cobertura_jurados": cobertura_jurados,
        "cobertura_turmas": cobertura_turmas,
        "total_sem_avaliacao": sum(len(t["sem_avaliacao"]) for t in cobertura_turmas),
        "total_avaliacoes": len(avaliacoes),
        "digitadores": sorted(digitadores.items(), key=lambda item: item[0][1]),
        "digitador": digitador,
        "linhas": linhas,
    }


def _concluir(request, edicao):
    if edicao.banca_conferida_em is not None:
        return JA_CONFERIDA
    if edicao.votacao_encerrada_em is None:
        return NAO_ENCERRADA
    avaliacoes = Avaliacao.objects.filter(jurado__edicao=edicao)
    if not avaliacoes.exists():
        return SEM_AVALIACOES
    if avaliacoes.filter(digitado_por=request.user).exists():  # `alterado_por` não impede
        return QUEM_DIGITOU
    edicao.banca_conferida_em = timezone.now()
    edicao.save(update_fields=["banca_conferida_em"])
    _registrar(request, edicao, f"Conferência da banca concluída por {request.user.get_username()}")
    messages.success(request, "Conferência concluída.")
    return None


def _reabrir(request, edicao):
    if edicao.banca_conferida_em is None:
        return NAO_CONFERIDA
    edicao.banca_conferida_em = None
    edicao.save(update_fields=["banca_conferida_em"])
    _registrar(request, edicao, f"Digitação reaberta por {request.user.get_username()}")
    messages.success(request, "Digitação reaberta: a conferência foi desfeita e os jurados voltam à digitação.")
    return None


ACOES = {"concluir": _concluir, "reabrir": _reabrir}


def _registrar(request, edicao, mensagem):
    LogEntry.objects.log_actions(
        user_id=request.user.pk, queryset=[edicao], action_flag=CHANGE, change_message=mensagem, single_object=True
    )


def _executar(request, id):
    acao = ACOES.get(request.POST.get("acao"))
    with transaction.atomic():
        edicao = get_object_or_404(Edicao.objects.select_for_update(), pk=id)
        recusa = acao(request, edicao) if acao else "Ação inválida."
    if recusa:
        messages.error(request, recusa)
    return redirect(_url(edicao.pk))
