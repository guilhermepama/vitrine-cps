"""Ranking por turma com participação (specs/04-resultados.md, fatia 2).

Só leitura e só agregados: nenhuma linha identifica um token, e de visitante
só sai a contagem. As views buscam os dados e chamam `calcular_ranking`; a
regra do cálculo mora em `resultados/calculo.py` e a nota da banca vem
pronta de `banca.servicos.nota_banca_por_projeto`.

Acesso (ordem da spec, antes de qualquer consulta a dados de negócio):
anônimo → login do admin; logado sem `is_active`/`is_staff` → 403, mesmo com
a permissão; staff sem a permissão da rota → 403; edição inexistente → 404.

Número fixo de consultas, independente de quantas turmas, projetos e votos a
edição tem: cada dado vem de uma consulta agregada só.
"""

from decimal import Decimal
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.handlers.exception import response_for_exception
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from banca.servicos import nota_banca_por_projeto
from cadastro.models import Edicao, Projeto
from resultados.calculo import PesosInvalidos, ProjetoEntrada, TurmaEntrada, calcular_ranking
from votacao.models import Token, Visitante, Voto

VER_RESULTADOS = "resultados.ver_resultados"


def exige_admin_com(permissao):
    """Admin (ativo + staff) com a permissão da rota; superusuário tem todas."""

    def decorador(view):
        @wraps(view)
        def protegida(request, *args, **kwargs):
            usuario = request.user
            if not usuario.is_authenticated:
                return redirect_to_login(request.get_full_path(), reverse("admin:login"))
            try:
                if not (usuario.is_active and usuario.is_staff and usuario.has_perm(permissao)):
                    raise PermissionDenied
                return view(request, *args, **kwargs)
            except (PermissionDenied, Http404) as excecao:
                # Resposta do handler padrão aqui dentro, para o never_cache
                # de fora também marcar o 403/404 como no-store.
                return response_for_exception(request, excecao)

        return protegida

    return decorador


def _votos_da_edicao(edicao):
    """Votos em projetos da edição dados por tokens de estações da edição."""
    return Voto.objects.filter(projeto__turma__edicao=edicao, token__estacao__edicao=edicao)


def _turmas(edicao):
    """Turmas da edição com os projetos `publicado` (o filtro da cédula), na
    ordem da turma; turma sem projeto publicado não aparece. Uma consulta."""
    projetos = (
        Projeto.objects.filter(turma__edicao=edicao, status=Projeto.Status.PUBLICADO)
        .select_related("turma__curso")
        .order_by(
            "turma__curso__sigla",
            "turma__tipo_periodo",
            "turma__numero_periodo",
            "turma__turno",
            "turma_id",
            "titulo",
            "id",
        )
    )
    turmas = {}
    for projeto in projetos:
        nome, lista = turmas.setdefault(projeto.turma_id, (projeto.turma.rotulo, []))
        lista.append(ProjetoEntrada(projeto.id, projeto.titulo))
    return [TurmaEntrada(turma_id, nome, tuple(lista)) for turma_id, (nome, lista) in turmas.items()]


def _participacao(edicao, turmas, por_turma):
    """Contagens agregadas da edição; por turma só com `por_turma` (votação
    encerrada — parecer do #54). Até quatro consultas."""
    votos = _votos_da_edicao(edicao)
    geral = votos.aggregate(total=Count("id"), tokens=Count("token", distinct=True))
    contagens = {}
    if por_turma:
        contagens = {
            linha["projeto__turma_id"]: linha
            for linha in votos.values("projeto__turma_id").annotate(
                total=Count("id"), tokens=Count("token", distinct=True)
            )
        }
    media = Decimal(geral["total"]) / Decimal(geral["tokens"]) if geral["tokens"] else None
    return {
        "tokens_emitidos": Token.objects.filter(estacao__edicao=edicao).count(),
        "tokens_votantes": geral["tokens"],
        "total_votos": geral["total"],
        "media_por_token": media,
        # Pela edição do visitante, nunca pelo token (G6, ADR-003).
        "visitantes": Visitante.objects.filter(edicao=edicao).count(),
        # None antes de encerrar: numa turma de um projeto só, o total da
        # turma seria o parcial do projeto (spec 04, "Participação").
        "turmas": [
            {
                "nome": turma.nome,
                "votos": contagens.get(turma.id, {}).get("total", 0),
                "tokens": contagens.get(turma.id, {}).get("tokens", 0),
            }
            for turma in turmas
        ]
        if por_turma
        else None,
    }


def _ranking(edicao, turmas):
    """(ranking, erro). Só chamado com a votação encerrada. Duas consultas."""
    votos = dict(
        _votos_da_edicao(edicao).values("projeto_id").annotate(n=Count("id")).values_list("projeto_id", "n")
    )
    try:
        ranking = calcular_ranking(
            turmas,
            votos,
            nota_banca_por_projeto(edicao),
            edicao.peso_banca,
            edicao.peso_publico,
            banca_conferida=edicao.banca_conferida_em is not None,
        )
    except PesosInvalidos as erro:
        return None, str(erro)
    return ranking, None


# never_cache por fora: até o 405 do require_GET sai com no-store.
@never_cache
@require_GET
@exige_admin_com(VER_RESULTADOS)
def ranking(request, edicao_id):
    edicao = get_object_or_404(Edicao, pk=edicao_id)
    turmas = _turmas(edicao)
    encerrada = edicao.votacao_encerrada_em is not None
    contexto = {
        "edicao": edicao,
        "participacao": _participacao(edicao, turmas, por_turma=encerrada),
        "aviso": None,
        "erro": None,
        "ranking": None,
    }
    if edicao.votacao_aberta_em is None:
        contexto["aviso"] = "Votação desta edição não foi configurada"
    elif not encerrada:
        contexto["aviso"] = "Resultado disponível após o encerramento da votação"
    else:
        contexto["ranking"], contexto["erro"] = _ranking(edicao, turmas)
    return render(request, "resultados/ranking.html", contexto)
