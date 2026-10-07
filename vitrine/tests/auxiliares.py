"""Dados e atalhos dos testes da vitrine (spec 02)."""

import itertools
import re
from datetime import timedelta

from django.utils import timezone

from cadastro.models import Curso, Projeto
from cadastro.seguranca import hash_ra
from cadastro.tests import fabricas

RA = "1234567890123"
_numero = itertools.count(1)


def nova_edicao(**campos):
    """Edição com nome único (o nome é único no banco) e, por padrão, ativa."""
    campos.setdefault("ativa", True)
    return fabricas.edicao(nome=f"Edição {next(_numero)}", **campos)


def projeto_reivindicavel(ra=RA, edicao=None, **campos):
    """Projeto recém-importado: `pre_cadastrado`, RA do representante, edição ativa."""
    edicao = edicao or nova_edicao()
    return fabricas.projeto(fabricas.turma(edicao), ra_hmac=hash_ra(ra), **campos)


def projeto_com_link(status=Projeto.Status.PRE_CADASTRADO, unidade=Curso.Unidade.FATEC, edicao=None, **campos):
    """Projeto já reivindicado, com o token de edição em claro."""
    edicao = edicao or nova_edicao()
    turma = fabricas.turma(edicao, fabricas.curso(sigla=f"C{next(_numero)}", unidade=unidade))
    projeto = fabricas.projeto(turma, reivindicado_em=timezone.now(), **campos)
    token = projeto.regerar_link()
    if status != Projeto.Status.PRE_CADASTRADO:
        projeto.status = status
        projeto.save(update_fields=["status", "atualizado_em"])
    return projeto, token


def com_capa(projeto):
    projeto.capa = fabricas.imagem()
    projeto.save(update_fields=["capa", "atualizado_em"])
    return projeto


def dados_de_edicao(
    resumo="Um resumo do projeto.",
    descricao="Uma descrição mais longa.",
    integrantes=(("Ana", "Front-end"),),
    acao="salvar",
    **extra,
):
    dados = {
        "resumo": resumo,
        "descricao": descricao,
        "componente_origem": "",
        "link_repositorio": "",
        "link_demo": "",
        "link_video": "",
        "acao": acao,
        "integrantes-TOTAL_FORMS": str(len(integrantes)),
        "integrantes-INITIAL_FORMS": "0",
        "integrantes-MIN_NUM_FORMS": "0",
        "integrantes-MAX_NUM_FORMS": "10",
    }
    for i, (nome, papel) in enumerate(integrantes):
        dados[f"integrantes-{i}-nome"] = nome
        dados[f"integrantes-{i}-papel"] = papel
    dados.update(extra)
    return dados


def prazo_vencido(projeto):
    edicao = projeto.turma.edicao
    edicao.prazo_edicao = timezone.now() - timedelta(minutes=1)
    edicao.save()


def votacao_aberta(projeto):
    edicao = projeto.turma.edicao
    edicao.votacao_aberta_em = timezone.now() - timedelta(minutes=1)
    edicao.save()


def sem_csrf(html):
    """O token CSRF muda a cada render: tira do HTML para comparar páginas."""
    return re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', 'name="csrfmiddlewaretoken" value="X"', html)
