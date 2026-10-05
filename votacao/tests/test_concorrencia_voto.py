"""Concorrência do voto — fatia F6 (specs/03-credenciamento-votacao.md).

Threads de verdade, cada uma com a sua conexão ao Postgres
(`django_db(transaction=True)`: os commits acontecem de fato).

Critérios de aceite fechados aqui:
- "Teste de corrida: 2 POSTs simultâneos (mesmo token+projeto) → 1 voto no
  banco; o outro recebe 409 genérico".
- "Teste de concorrência: voto que obtém a trava depois do encerramento →
  409 e nenhum voto gravado; voto que obteve a trava antes → gravado".
"""

import threading
import time
from unittest import mock

import pytest
from django.db import connection
from django.test import Client
from django.utils import timezone

from votacao import servicos, views_voto
from votacao.models import Voto
from votacao.servicos import encerrar_votacao
from votacao.tests.cenario import montar

pytestmark = pytest.mark.django_db(transaction=True)

ROTA = "/votos"
PRAZO = 10  # segundos; nenhuma espera do teste passa disso


@pytest.fixture
def cenario():
    return montar()


class Tarefa(threading.Thread):
    """Thread que guarda o resultado (ou a exceção) e fecha a própria conexão."""

    def __init__(self, alvo):
        super().__init__(daemon=True)
        self.alvo, self.resultado, self.erro = alvo, None, None

    def run(self):
        try:
            self.resultado = self.alvo()
        except BaseException as erro:  # noqa: BLE001 — repassado no join
            self.erro = erro
        finally:
            connection.close()

    def fim(self):
        self.join(PRAZO)
        assert not self.is_alive(), "thread presa"
        if self.erro:
            raise self.erro
        return self.resultado


def _esperar_alguem_na_fila_da_trava():
    """Espera até uma conexão do banco de teste estar parada esperando trava."""
    limite = time.monotonic() + PRAZO
    while time.monotonic() < limite:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )
            if cursor.fetchone()[0]:
                return
        time.sleep(0.02)
    pytest.fail("ninguém entrou na fila da trava")


def _votar(cenario, projeto):
    def votar():
        return cenario.votante(Client()).post(ROTA, {"projeto_id": str(projeto.pk)})

    return votar


def test_dois_posts_simultaneos_do_mesmo_token_e_projeto_gravam_um_voto(cenario):
    barreira = threading.Barrier(2)
    votar = _votar(cenario, cenario.publicado)

    def na_largada():
        barreira.wait(PRAZO)
        return votar()

    tarefas = [Tarefa(na_largada) for _ in range(2)]
    for tarefa in tarefas:
        tarefa.start()
    respostas = [tarefa.fim() for tarefa in tarefas]
    assert sorted(r.status_code for r in respostas) == [201, 409]
    perdedor = next(r for r in respostas if r.status_code == 409)
    assert perdedor.content == views_voto.REJEITADO
    assert Voto.objects.count() == 1


def test_voto_que_pega_a_trava_depois_do_encerramento_e_rejeitado(cenario):
    travou, soltar = threading.Event(), threading.Event()
    agora_real = timezone.now

    def agora_depois_de_soltar():
        # Chamado pelo encerrar_votacao com a linha da Edicao já travada.
        travou.set()
        assert soltar.wait(PRAZO)
        return agora_real()

    # Só o `timezone` visto por servicos.py: o resto do Django segue com o relógio real.
    relogio = mock.Mock(now=mock.Mock(side_effect=agora_depois_de_soltar))
    with mock.patch.object(servicos, "timezone", relogio):
        encerramento = Tarefa(lambda: encerrar_votacao(cenario.evento.pk))
        encerramento.start()
        assert travou.wait(PRAZO)
        voto = Tarefa(_votar(cenario, cenario.publicado))
        voto.start()
        _esperar_alguem_na_fila_da_trava()
        soltar.set()
        assert encerramento.fim() is None
        resposta = voto.fim()
    assert (resposta.status_code, resposta.content) == (409, views_voto.REJEITADO)
    assert Voto.objects.count() == 0


def test_voto_que_pegou_a_trava_antes_do_encerramento_e_gravado(cenario):
    travou, soltar = threading.Event(), threading.Event()
    cadastro_valido = views_voto.cadastro_valido

    def conferir_depois_de_soltar(request, edicao):
        # Chamado pelo voto com a linha da Edicao já travada.
        travou.set()
        assert soltar.wait(PRAZO)
        return cadastro_valido(request, edicao)

    with mock.patch.object(views_voto, "cadastro_valido", side_effect=conferir_depois_de_soltar):
        voto = Tarefa(_votar(cenario, cenario.publicado))
        voto.start()
        assert travou.wait(PRAZO)
        encerramento = Tarefa(lambda: encerrar_votacao(cenario.evento.pk))
        encerramento.start()
        _esperar_alguem_na_fila_da_trava()
        soltar.set()
        resposta = voto.fim()
        assert encerramento.fim() is None
    assert resposta.status_code == 201
    gravado = Voto.objects.get()
    cenario.evento.refresh_from_db()
    assert gravado.criado_em < cenario.evento.votacao_encerrada_em
