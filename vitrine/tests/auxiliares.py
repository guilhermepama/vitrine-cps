"""Dados e atalhos dos testes da vitrine (spec 02)."""

import itertools
import re
from datetime import timedelta

from django.utils import timezone

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
