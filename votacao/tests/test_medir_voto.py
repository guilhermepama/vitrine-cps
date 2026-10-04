"""Ferramenta de medição da trava por voto — fatia F8 (nota N3 do plano).

Roda o comando contra o `live_server` do pytest-django (http local, sem rede
externa), num nível de concorrência pequeno. A medição de verdade é no
pré-ensaio de 21/10, no ambiente publicado.
"""

from datetime import date
from io import StringIO
from unittest import mock

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError

from cadastro.models import Projeto
from cadastro.tests import fabricas as cadastro
from votacao import assinatura
from votacao.management.commands import medir_voto
from votacao.models import Token, Visitante, Voto
from votacao.servicos import abrir_votacao
from votacao.tests import fabricas

PUBLICADO = Projeto.Status.PUBLICADO


def _edicao_em_votacao(nome, projetos=3, estacoes=2):
    edicao = cadastro.edicao(nome=nome, data_evento=date(2026, 10, 21))
    turma = cadastro.turma(edicao)
    for i in range(projetos):
        cadastro.projeto(turma, titulo=f"Projeto {i}", status=PUBLICADO)
    for i in range(estacoes):
        fabricas.estacao(edicao, nome=f"Estação {i}")
    assert abrir_votacao(edicao.pk) is None
    return edicao


def _medir(*args):
    saida = StringIO()
    call_command("medir_voto", *args, stdout=saida)
    return saida.getvalue()


@pytest.mark.django_db(transaction=True)
def test_mede_contra_o_servidor_e_respeita_o_fluxo(live_server):
    call_command("createcachetable", verbosity=0)
    _edicao_em_votacao("Pré-ensaio 2026/2")
    saida = _medir("--url", live_server.url, "--niveis", "1,3", "--votos", "2")
    linhas = saida.splitlines()
    assert "2 estação(ões), 4 emissão(ões)" in linhas[0]
    assert "  1 simultâneos |    2 votos" in linhas[1] and "201 2 409 0 5xx 0 outros 0" in linhas[1]
    assert "  3 simultâneos |    6 votos" in linhas[2] and "201 6 409 0 5xx 0 outros 0" in linhas[2]
    assert "p50" in linhas[1] and "p95" in linhas[1] and "máx" in linhas[1]
    # Um token e um cadastro por visitante simulado; votos em projetos diferentes.
    assert (Token.objects.count(), Visitante.objects.count(), Voto.objects.count()) == (4, 4, 8)
    assert settings.QR_HMAC_SECRET not in saida


@pytest.mark.django_db
@pytest.mark.parametrize("nome", ["2026/2", "Ensaio 2026/2", "Pre-ensaio 2026/2"])
def test_recusa_rodar_fora_do_pre_ensaio(nome):
    _edicao_em_votacao(nome)
    with pytest.raises(CommandError, match="pré-ensaio"):
        _medir("--url", "http://127.0.0.1:9")
    assert Token.objects.count() == 0


@pytest.mark.django_db
def test_recusa_sem_votacao_aberta():
    with pytest.raises(CommandError, match="pré-ensaio"):
        _medir("--url", "http://127.0.0.1:9")


@pytest.mark.django_db
def test_nome_em_maiusculas_tambem_vale_e_recusa_sem_estacao():
    _edicao_em_votacao("PRÉ-ENSAIO 2026/2", estacoes=0)
    with pytest.raises(CommandError, match="estação ativa"):
        _medir("--url", "http://127.0.0.1:9")


@pytest.mark.django_db
def test_nao_passa_do_limite_por_ip():
    _edicao_em_votacao("Pré-ensaio 2026/2")
    with pytest.raises(CommandError, match="300"):
        _medir("--url", "http://127.0.0.1:9", "--niveis", "200,101")
    assert Token.objects.count() == 0


def test_segredo_nao_e_argumento():
    parser = medir_voto.Command().create_parser("manage.py", "medir_voto")
    opcoes = {acao.dest for acao in parser._actions}
    assert {"url", "niveis", "votos"} <= opcoes
    assert not {o for o in opcoes if "segredo" in o or "secret" in o or "hmac" in o}


def test_distribuidor_nao_passa_de_20_por_estacao_e_bloco():
    relogio = {"agora": 1_793_000_010}  # início de bloco + 20 s

    def dormir(segundos):
        relogio["agora"] += segundos

    with (
        mock.patch.object(assinatura, "agora", side_effect=lambda: relogio["agora"]),
        mock.patch.object(medir_voto.time, "sleep", side_effect=dormir),
    ):
        distribuidor = medir_voto.Distribuidor([7, 8])
        primeiras = [distribuidor.proxima() for _ in range(40)]
        assert (primeiras.count(7), primeiras.count(8)) == (20, 20)
        bloco = relogio["agora"] // 45
        assert distribuidor.proxima() == 7
        assert relogio["agora"] // 45 == bloco + 1  # esperou o bloco seguinte


def test_resumo_conta_201_409_5xx_e_sem_resposta():
    resultados = [(201, 0.010), (201, 0.030), (409, 0.020), (500, 0.040), (0, 30.0)]
    linha = medir_voto.resumo(5, resultados)
    assert "5 votos" in linha
    assert "201 2 409 1 5xx 1 outros 1" in linha
    assert "p50    25.0 ms" in linha and "máx    40.0 ms" in linha
