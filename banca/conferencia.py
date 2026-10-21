"""Conferência da banca (spec 06, fatia 5).

Rota do `JuradoAdmin.get_urls()`, envolvida em `admin_site.admin_view`
(anônimo ou não staff → login do admin; `never_cache`; CSRF). Staff sem
`banca.concluir_conferencia` → 403; edição inexistente → 404.

GET: cobertura por jurado e por turma e a amostra a conferir (ou, com
`?digitador=<id>`, todas as avaliações daquele digitador). Número fixo de
consultas, independente do tamanho da edição.

POST (`acao`): "concluir" preenche `banca_conferida_em`, só se as avaliações
e notas ainda são as que a página mostrou (`versao`, conferida com a `Edicao`
travada; parecer do Renan no #58); "reabrir" (decisão
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
from banca.models import Avaliacao, Criterio, Jurado, Nota, Tipo
from cadastro.models import Edicao, Projeto, Turma

CONCLUIR_CONFERENCIA = "banca.concluir_conferencia"
AMOSTRA_MINIMA = 10

QUEM_DIGITOU = "Quem digitou fichas desta edição não pode concluir a conferência."
JA_CONFERIDA = "A conferência desta edição já foi concluída."
NAO_ENCERRADA = "A votação desta edição ainda não foi encerrada."
SEM_AVALIACOES = "Nenhuma avaliação digitada nesta edição."
NAO_CONFERIDA = "A conferência desta edição não está concluída; não há digitação a reabrir."
NOTAS_MUDARAM = (
    "As avaliações ou notas desta edição mudaram depois que você abriu a página. "
    "Confira de novo antes de concluir."
)


def versao_da_banca(edicao_id):
    """Marca do estado da banca: sha256 das avaliações (jurado, projeto) e das
    notas da edição. Qualquer digitação, correção ou exclusão muda a marca."""
    avaliacoes = Avaliacao.objects.filter(jurado__edicao_id=edicao_id).order_by("pk")
    notas = Nota.objects.filter(avaliacao__jurado__edicao_id=edicao_id).order_by("avaliacao_id", "criterio_id", "pk")
    estado = (
        list(avaliacoes.values_list("pk", "jurado_id", "projeto_id")),
        [(a, c, str(v)) for a, c, v in notas.values_list("avaliacao_id", "criterio_id", "valor")],
    )
    return hashlib.sha256(repr(estado).encode()).hexdigest()


def tamanho_da_amostra(total):
    """20% arredondado para cima, no mínimo 10 (ou todas, se houver menos)."""
    return min(total, max(AMOSTRA_MINIMA, -(-total // 5)))


def sortear_amostra(edicao_id, ids):
    """Mesma amostra em qualquer processo, até mudar o conjunto de avaliações:
    a semente é o sha256 de `edicao_id` e dos ids em ordem (nada de `hash()`)."""
    ids = sorted(ids)
    semente = hashlib.sha256(f"{edicao_id}:{','.join(map(str, ids))}".encode()).digest()
    return random.Random(semente).sample(ids, tamanho_da_amostra(len(ids)))


def id_valido(valor):
    """Só dígitos ASCII e no máximo 18 (cabe num bigint; `int()` de número
    gigante estoura o limite de dígitos do Python e daria 500)."""
    return valor.isascii() and valor.isdigit() and len(valor) <= 18


def _url(edicao_id):
    return reverse("admin:banca_jurado_conferencia", args=[edicao_id])


@require_http_methods(["GET", "POST"])
@exige_permissao(CONCLUIR_CONFERENCIA)
def conferencia(request, id, admin_site=admin.site):
    if request.method == "POST":
        return _executar(request, id)
    digitador = request.GET.get("digitador")
    if digitador is not None and not id_valido(digitador):
        messages.error(request, "Digitador inválido.")
        return redirect(_url(id))
    # Notas exibidas e versão lidas com a `Edicao` travada (a mesma trava de quem
    # corrige uma nota, pelos sinais): uma correção não cai entre as duas leituras.
    with transaction.atomic():
        edicao = get_object_or_404(Edicao.objects.select_for_update(), pk=id)
        contexto = _contexto(edicao, digitador and int(digitador))
    return render(request, "banca/conferencia.html", {**admin_site.each_context(request), **contexto})


def _tipos_da_edicao(edicao, jurados, criterios):
    """Banca sempre; convidados quando a edição os usa: peso no ranking, peso no
    boletim (`peso_boletim_banca < 1`), jurado ou critério convidado (ADR-013, spec 06)."""
    usa_convidados = (
        edicao.peso_convidados > 0
        or edicao.peso_boletim_banca < 1
        or any(j.tipo == Tipo.CONVIDADO for j in jurados)
        or any(c.tipo == Tipo.CONVIDADO for c in criterios)
    )
    return [Tipo.BANCA, Tipo.CONVIDADO] if usa_convidados else [Tipo.BANCA]


def _cobertura_parcial_de_curso(jurados, turmas_do_jurado, turmas, publicados):
    """Avisos de jurado que avalia só parte das turmas (com publicados) de um
    curso: com a normalização por curso, a nota mediria o jurado (ADR-013)."""
    turmas_do_curso = defaultdict(list)
    for turma in turmas:
        if publicados[turma.pk]:
            turmas_do_curso[turma.curso_id].append(turma)
    avisos = []
    for jurado in jurados:
        for curso_id, do_curso in turmas_do_curso.items():
            cobertas = [t for t in do_curso if t.pk in turmas_do_jurado[jurado.pk]]
            if cobertas and len(cobertas) < len(do_curso):
                faltam = [t.rotulo for t in do_curso if t.pk not in turmas_do_jurado[jurado.pk]]
                avisos.append(
                    f"{jurado.nome} ({jurado.get_tipo_display().lower()}) avalia "
                    f"{', '.join(t.rotulo for t in cobertas)}, mas não {', '.join(faltam)}."
                )
    return avisos


def _contexto(edicao, digitador):
    turmas = list(Turma.objects.filter(edicao=edicao).select_related("curso").order_by(*ORDEM_TURMA))
    jurados = list(Jurado.objects.filter(edicao=edicao).order_by("nome"))
    tipo_do_jurado = {j.pk: j.tipo for j in jurados}
    criterios_todos = list(Criterio.objects.filter(edicao=edicao).order_by("tipo", "ordem"))
    tipos = _tipos_da_edicao(edicao, jurados, criterios_todos)
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
    por_projeto = Counter((a[2], tipo_do_jurado.get(a[1])) for a in avaliacoes)
    digitadores = Counter((a[3], a[4]) for a in avaliacoes)

    cobertura_turmas = []
    for turma in turmas:
        projetos = publicados[turma.pk]
        por_tipo = []
        for tipo in tipos:
            n = sum(1 for j in jurados_da_turma[turma.pk] if tipo_do_jurado.get(j) == tipo)
            por_tipo.append(
                {
                    "tipo": tipo,
                    "convidado": tipo == Tipo.CONVIDADO,
                    "jurados": n,
                    "sem_avaliacao": [p for p in projetos if not por_projeto[(p.pk, tipo)]],
                    "incompletos": [
                        (p, por_projeto[(p.pk, tipo)]) for p in projetos if 0 < por_projeto[(p.pk, tipo)] < n
                    ],
                }
            )
        cobertura_turmas.append(
            {
                "turma": turma,
                "publicados": len(projetos),
                "jurados": por_tipo[0]["jurados"],
                "tipos": por_tipo,
                "completa": not any(t["sem_avaliacao"] or t["incompletos"] for t in por_tipo),
            }
        )
    grupos_jurados = [
        {
            "tipo": tipo,
            "rotulo": "Avaliadores convidados" if tipo == Tipo.CONVIDADO else "Banca",
            "linhas": [
                (jurado, por_jurado[jurado.pk], sum(len(publicados[t]) for t in turmas_do_jurado[jurado.pk]))
                for jurado in jurados
                if jurado.tipo == tipo
            ],
        }
        for tipo in tipos
    ]

    if digitador is None:
        ids = sortear_amostra(edicao.pk, [a[0] for a in avaliacoes])
    else:
        ids = [a[0] for a in avaliacoes if a[3] == digitador]
    criterios = {tipo: [c for c in criterios_todos if c.tipo == tipo] for tipo in tipos}
    linhas = defaultdict(list)
    notas = Prefetch("notas", queryset=Nota.objects.only("avaliacao_id", "criterio_id", "valor"))
    for avaliacao in (
        Avaliacao.objects.filter(pk__in=ids)
        .select_related("jurado", "projeto", "digitado_por")
        .prefetch_related(notas)
        .order_by("jurado__nome", "projeto_id")
    ):
        valores = {nota.criterio_id: nota.valor for nota in avaliacao.notas.all()}
        tipo = avaliacao.jurado.tipo
        linhas[tipo].append((avaliacao, [valores.get(c.pk) for c in criterios.get(tipo, [])]))
    amostras = [
        {
            "tipo": tipo,
            "convidado": tipo == Tipo.CONVIDADO,
            "criterios": criterios[tipo],
            "colunas": len(criterios[tipo]) + 3,  # jurado, projeto, digitador e uma por critério
            "linhas": linhas[tipo],
        }
        for tipo in tipos
    ]

    return {
        "title": f"Conferência da banca — {edicao.nome}",
        "edicao": edicao,
        "varios_tipos": len(tipos) > 1,
        "grupos_jurados": grupos_jurados,
        "cobertura_turmas": cobertura_turmas,
        "cobertura_parcial": _cobertura_parcial_de_curso(jurados, turmas_do_jurado, turmas, publicados),
        "total_sem_avaliacao": sum(len(t["sem_avaliacao"]) for item in cobertura_turmas for t in item["tipos"]),
        "total_avaliacoes": len(avaliacoes),
        "total_na_amostra": sum(len(a["linhas"]) for a in amostras),
        "digitadores": sorted(digitadores.items(), key=lambda item: item[0][1]),
        "digitador": digitador,
        "amostras": amostras,
        "versao": versao_da_banca(edicao.pk),
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
    # A `Edicao` está travada (_executar) e toda correção passa por ela (sinais):
    # a marca relida aqui é a que vale até o commit.
    if request.POST.get("versao") != versao_da_banca(edicao.pk):
        return NOTAS_MUDARAM
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
