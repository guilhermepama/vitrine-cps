"""Dados da página inicial e da página de projetos (spec 07), separados da view para testar sem HTTP.

Só leitura: projetos publicados da edição ativa, agrupados por turma.
"""

import random
from dataclasses import dataclass, field

from django.db.models import Count
from django.utils import timezone

from cadastro.models import Curso, Edicao, Projeto

_UNIDADES = {
    0: ("zero", "zero"), 1: ("um", "uma"), 2: ("dois", "duas"), 3: ("três", "três"), 4: ("quatro", "quatro"),
    5: ("cinco", "cinco"), 6: ("seis", "seis"), 7: ("sete", "sete"), 8: ("oito", "oito"), 9: ("nove", "nove"),
    10: ("dez", "dez"), 11: ("onze", "onze"), 12: ("doze", "doze"), 13: ("treze", "treze"),
    14: ("catorze", "catorze"), 15: ("quinze", "quinze"), 16: ("dezesseis", "dezesseis"),
    17: ("dezessete", "dezessete"), 18: ("dezoito", "dezoito"), 19: ("dezenove", "dezenove"), 20: ("vinte", "vinte"),
}


def contagem(n, singular, plural, feminino=False):
    """"oito projetos", "uma turma"; acima de vinte, em algarismos ("23 projetos")."""
    numero = _UNIDADES[n][feminino] if n in _UNIDADES else str(n)
    return f"{numero} {singular if n == 1 else plural}"


@dataclass
class GrupoTurma:
    turma: object
    projetos: list = field(default_factory=list)

    @property
    def curso(self):
        return self.turma.curso

    @property
    def periodo_curto(self):
        """"DSM · 3º sem", para caber na linha do cartão."""
        abreviado = {"semestre": "sem", "ano": "ano", "modulo": "mód"}[self.turma.tipo_periodo]
        return f"{self.curso.sigla} · {self.turma.numero_periodo}º {abreviado}"


def _ordem_turma(turma):
    """Fatec antes de Etec, sigla do curso, período do maior para o menor, turno."""
    return (turma.curso.unidade != Curso.Unidade.FATEC, turma.curso.sigla, -turma.numero_periodo, turma.turno)


def turmas_publicadas(edicao):
    """[GrupoTurma] só com projetos `publicado` da edição; consultas constantes."""
    projetos = (
        Projeto.objects.filter(turma__edicao=edicao, status=Projeto.Status.PUBLICADO)
        .select_related("turma__curso")
        .annotate(n_integrantes=Count("integrantes"))
        .order_by("titulo", "pk")
    )
    grupos = {}
    for projeto in projetos:
        grupos.setdefault(projeto.turma_id, GrupoTurma(projeto.turma)).projetos.append(projeto)
    return sorted(grupos.values(), key=lambda grupo: _ordem_turma(grupo.turma))


def links_do_projeto(projeto):
    nomes = [("Repositório", projeto.link_repositorio), ("demo", projeto.link_demo), ("vídeo", projeto.link_video)]
    presentes = [nome for nome, url in nomes if url]
    if not presentes:
        return "—"
    texto = " · ".join(presentes)
    return texto[0].upper() + texto[1:]


# Quantos cartões a home mostra; a lista completa fica em /projetos/.
QUANTIDADE_NA_HOME = 4


def _projetos_da_edicao_ativa():
    """Edição ativa, turmas com os projetos já prontos para o cartão, total e título da seção."""
    edicao = Edicao.objects.ativa()
    turmas = turmas_publicadas(edicao) if edicao else []
    for grupo in turmas:
        for projeto in grupo.projetos:
            projeto.links_resumo = links_do_projeto(projeto)
            projeto.periodo_curto = grupo.periodo_curto
    total = sum(len(grupo.projetos) for grupo in turmas)
    contexto = {"edicao": edicao, "turmas": turmas, "total_projetos": total}
    if total:
        contexto["titulo_projetos"] = (
            f"{contagem(total, 'projeto', 'projetos').capitalize()}, "
            f"{contagem(len(turmas), 'turma', 'turmas', feminino=True)}"
        )
    return contexto


def sortear_destaques(turmas, quantidade=QUANTIDADE_NA_HOME, sorteio=None):
    """Sorteia os cartões da home a cada visita, mantendo a ordem das turmas entre eles.

    Sorteio e não "os primeiros": pela ordem das turmas, a home mostraria sempre
    a mesma turma, e numa mostra com votação a vitrine fixa favorece um grupo.
    """
    sorteio = sorteio or random.sample
    todos = [projeto for grupo in turmas for projeto in grupo.projetos]
    escolhidos = sorted(sorteio(range(len(todos)), min(quantidade, len(todos))))
    return [todos[i] for i in escolhidos]


def contexto_da_pagina_inicial():
    contexto = _projetos_da_edicao_ativa()
    contexto["destaques"] = sortear_destaques(contexto.pop("turmas"))
    edicao = contexto["edicao"]
    if edicao:
        contexto["evento_passou"] = edicao.data_evento < timezone.localdate()
        contexto["percentual_banca"] = round(edicao.peso_banca * 100)
        contexto["percentual_publico"] = round(edicao.peso_publico * 100)
        # peso_convidados chega com a ADR-013 (#81); até lá o termo fica fora da premiação.
        peso_convidados = getattr(edicao, "peso_convidados", None)
        if peso_convidados:
            contexto["percentual_convidados"] = round(peso_convidados * 100)
    return contexto


def contexto_da_pagina_da_semana():
    """Semana da Tecnologia: edição ativa e 4 projetos sorteados a cada visita, pelo mesmo mecanismo da home, com o total para o botão."""
    contexto = _projetos_da_edicao_ativa()
    contexto["destaques"] = sortear_destaques(contexto.pop("turmas"))
    return contexto


def contexto_da_pagina_de_projetos():
    contexto = _projetos_da_edicao_ativa()
    cursos = []
    for grupo in contexto["turmas"]:
        if grupo.curso not in cursos:
            cursos.append(grupo.curso)
    contexto["cursos"] = cursos
    return contexto
