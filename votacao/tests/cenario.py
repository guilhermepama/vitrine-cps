"""Cenário da cédula e do voto (F6): evento em votação e ensaio separado,
cada um com turma, projetos e estação próprios (spec 03, "Isolamento por
edição")."""

from dataclasses import dataclass
from datetime import date

from cadastro.models import Edicao, Projeto
from cadastro.tests import fabricas as cadastro
from votacao.cookie_token import COOKIE_TOKEN
from votacao.liberacao import COOKIE_CADASTRO, valor_do_cookie
from votacao.models import Token
from votacao.servicos import abrir_votacao
from votacao.tests import fabricas

PUBLICADO = Projeto.Status.PUBLICADO


@dataclass
class Cenario:
    evento: Edicao
    ensaio: Edicao
    publicado: Projeto
    outro_publicado: Projeto
    em_revisao: Projeto
    do_ensaio: Projeto
    token: Token
    token_ensaio: Token

    def votante(self, client, token=None, cadastro_de=None):
        """Client com cookie do token e cookie de cadastro (do evento, por padrão)."""
        client.cookies[COOKIE_TOKEN] = str((token or self.token).pk)
        client.cookies[COOKIE_CADASTRO] = valor_do_cookie(cadastro_de or self.evento)
        return client


def montar():
    """Projetos criados antes de abrir a votação (depois, o status fica travado)."""
    evento = cadastro.edicao()
    ensaio = cadastro.edicao(nome="Ensaio 2026/2", data_evento=date(2026, 10, 22))
    dsm = cadastro.curso("DSM")
    turma = cadastro.turma(evento, dsm)
    outra_turma = cadastro.turma(evento, cadastro.curso("ADS"))
    turma_ensaio = cadastro.turma(ensaio, dsm)
    publicado = cadastro.projeto(turma, titulo="Agenda Escolar", status=PUBLICADO)
    outro_publicado = cadastro.projeto(outra_turma, titulo="Horta Viva", status=PUBLICADO)
    em_revisao = cadastro.projeto(turma, titulo="Rascunho Oculto", status=Projeto.Status.EM_REVISAO)
    do_ensaio = cadastro.projeto(turma_ensaio, titulo="Projeto do Ensaio", status=PUBLICADO)
    assert abrir_votacao(evento.pk) is None
    evento.refresh_from_db()
    return Cenario(
        evento=evento,
        ensaio=ensaio,
        publicado=publicado,
        outro_publicado=outro_publicado,
        em_revisao=em_revisao,
        do_ensaio=do_ensaio,
        token=fabricas.token(fabricas.estacao(evento)),
        token_ensaio=fabricas.token(fabricas.estacao(ensaio, nome="Entrada do ensaio")),
    )
