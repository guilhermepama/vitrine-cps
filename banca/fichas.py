"""Ficha da banca para imprimir (spec 06, fatia 4).

Rotas do `JuradoAdmin.get_urls()`, envolvidas em `admin_site.admin_view`
(anônimo ou não staff → login do admin; `never_cache`). Staff sem
`banca.imprimir_ficha` → 403, antes de qualquer consulta a dados da banca;
jurado ou edição inexistente → 404.

Número fixo de consultas, independente de quantos jurados, turmas e projetos:
jurados (com a edição), turmas dos jurados, critérios e projetos publicados,
uma consulta cada. Da ficha só saem número (`id`) e título do projeto: nada de
RA, representante, integrantes ou link de edição.
"""

from collections import defaultdict
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.core.handlers.exception import response_for_exception
from django.db.models import Prefetch, prefetch_related_objects
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from banca.models import Criterio, Jurado
from cadastro.models import Edicao, Projeto, Turma

IMPRIMIR_FICHA = "banca.imprimir_ficha"
ORDEM_TURMA = ["curso__sigla", "tipo_periodo", "numero_periodo", "turno", "id"]


def exige_imprimir_ficha(view):
    """O `admin_view` de fora já garantiu staff ativo; aqui, a permissão."""

    @wraps(view)
    def protegida(request, *args, **kwargs):
        try:
            if not request.user.has_perm(IMPRIMIR_FICHA):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        except (PermissionDenied, Http404) as excecao:
            # Resposta montada aqui dentro para o never_cache do admin_view
            # também marcar o 403/404 como no-store.
            return response_for_exception(request, excecao)

    return protegida


def _fichas(edicao, jurados):
    """Uma ficha por jurado: suas turmas (na ordem da turma), cada uma com os
    projetos publicados por título. Turma sem publicado fica de fora."""
    turmas = Prefetch("turmas", queryset=Turma.objects.select_related("curso").order_by(*ORDEM_TURMA))
    prefetch_related_objects(jurados, turmas)
    ids_turmas = {turma.pk for jurado in jurados for turma in jurado.turmas.all()}
    projetos = defaultdict(list)
    publicados = (
        Projeto.objects.filter(turma_id__in=ids_turmas, turma__edicao=edicao, status=Projeto.Status.PUBLICADO)
        .only("id", "titulo", "turma_id")
        .order_by("titulo", "id")
    )
    for projeto in publicados:
        projetos[projeto.turma_id].append(projeto)
    return [
        {
            "jurado": jurado,
            "turmas": [(turma, projetos[turma.pk]) for turma in jurado.turmas.all() if projetos[turma.pk]],
        }
        for jurado in jurados
    ]


def _render(request, edicao, jurados, titulo):
    criterios = list(Criterio.objects.filter(edicao=edicao).order_by("ordem"))
    contexto = {
        "titulo": titulo,
        "edicao": edicao,
        "provisoria": not edicao.votacao_foi_aberta(),
        "criterios": criterios,
        "colunas": len(criterios) + 2,  # Nº, Projeto e uma por critério
        "fichas": _fichas(edicao, jurados),
        "gerada_em": timezone.now(),
    }
    return render(request, "banca/ficha.html", contexto)


@require_GET
@exige_imprimir_ficha
def ficha_do_jurado(request, id):
    jurado = get_object_or_404(Jurado.objects.select_related("edicao"), pk=id)
    return _render(request, jurado.edicao, [jurado], f"Ficha da banca — {jurado.nome}")


@require_GET
@exige_imprimir_ficha
def fichas_da_edicao(request, id):
    edicao = get_object_or_404(Edicao, pk=id)
    jurados = list(Jurado.objects.filter(edicao=edicao).order_by("nome"))
    return _render(request, edicao, jurados, "Fichas da banca")
