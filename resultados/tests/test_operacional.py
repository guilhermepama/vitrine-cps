"""Relatório operacional (specs/04-resultados.md, fatia 3): emissões de token
por estação da edição — total, primeira e última emissão.

Critérios de aceite fechados aqui:
- Estação sem emissão → total 0 e primeira/última emissão "—"
- Soma dos totais por estação igual ao total de tokens emitidos da edição
- Nenhuma tela mostra ID de token ou IP
- Tokens e estações de outra edição não entram no relatório
- Número fixo de consultas (não cresce com estações e tokens)
"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from cadastro.tests import fabricas as cadastro
from resultados.tests import cenario
from votacao.models import Token
from votacao.tests import fabricas as votacao

pytestmark = pytest.mark.django_db

BRASILIA = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def admin(client):
    client.force_login(cenario.usuario())
    return client


def abrir(client, edicao):
    resposta = client.get(reverse("resultados:operacional", args=[edicao.pk]))
    assert resposta.status_code == 200
    return resposta, re.sub(r">\s+<", "><", resposta.content.decode())


def emitir(estacao, *momentos):
    """Tokens da estação com `criado_em` fixo (auto_now_add ignora o valor)."""
    tokens = []
    for momento in momentos:
        token = votacao.token(estacao)
        Token.objects.filter(pk=token.pk).update(criado_em=momento)
        tokens.append(token)
    return tokens


def hora(dia, h, m):
    return datetime(2026, 10, dia, h, m, tzinfo=BRASILIA)


def test_total_primeira_e_ultima_por_estacao_no_horario_local(admin):
    ed = cadastro.edicao()
    entrada = votacao.estacao(ed, nome="Entrada")
    # 22h30 em Brasília é 01h30 do dia 30 em UTC: a tela mostra o local.
    emitir(entrada, hora(29, 19, 5), hora(29, 22, 30), hora(29, 20, 0))
    _, html = abrir(admin, ed)
    assert "<td>Entrada</td><td class=\"n\">3</td><td>29/10/2026 19:05</td><td>29/10/2026 22:30</td>" in html


def test_estacao_sem_emissao_total_zero_e_tracos(admin):
    ed = cadastro.edicao()
    votacao.estacao(ed, nome="Biblioteca")
    resposta, html = abrir(admin, ed)
    assert "<td>Biblioteca</td><td class=\"n\">0</td><td>—</td><td>—</td>" in html
    assert resposta.context["total"] == 0


def test_soma_das_estacoes_igual_ao_total_de_tokens_da_edicao(admin):
    ed = cadastro.edicao()
    a, b, c = (votacao.estacao(ed, nome=n) for n in ("A", "B", "C"))
    emitir(a, hora(29, 19, 0), hora(29, 19, 1))
    emitir(b, *[hora(29, 20, i) for i in range(5)])
    resposta, html = abrir(admin, ed)
    totais = [e["total"] for e in resposta.context["estacoes"]]
    assert totais == [2, 5, 0]
    assert sum(totais) == resposta.context["total"] == Token.objects.filter(estacao__edicao=ed).count() == 7
    assert "<th>Total da edição</th><td class=\"n\">7</td>" in html


def test_outra_edicao_nao_entra(admin):
    evento, ensaio = cadastro.edicao(nome="2026/2"), cadastro.edicao(nome="Ensaio 2026/2")
    emitir(votacao.estacao(evento, nome="Entrada"), hora(29, 19, 0))
    emitir(votacao.estacao(ensaio, nome="Estação do ensaio"), hora(22, 19, 0), hora(22, 21, 0))
    resposta, html = abrir(admin, evento)
    assert [e["nome"] for e in resposta.context["estacoes"]] == ["Entrada"]
    assert resposta.context["total"] == 1
    assert "Estação do ensaio" not in html and "22/10/2026" not in html


def test_sem_id_de_token_ip_nem_visitante(admin):
    ed = cadastro.edicao()
    tokens = emitir(votacao.estacao(ed), hora(29, 19, 0), hora(29, 19, 30))
    votacao.visitante(ed, nome="Fulana Fictícia", email="fulana@example.com")
    _, html = abrir(admin, ed)
    for token in tokens:
        assert str(token.pk) not in html and token.pk.hex not in html
    assert "Fulana" not in html and "fulana@example.com" not in html
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", html)


def test_disponivel_com_a_votacao_aberta(admin):
    ed, _ = cenario.edicao({"DSM": [("Agenda", 2, 8)]}, estado="aberta")
    resposta, _ = abrir(admin, ed)
    assert resposta.context["total"] == 2


def test_nome_da_estacao_sai_escapado(admin):
    ed = cadastro.edicao()
    votacao.estacao(ed, nome="<b>Hall</b>")
    _, html = abrir(admin, ed)
    assert "&lt;b&gt;Hall&lt;/b&gt;" in html and "<b>Hall" not in html


def test_edicao_sem_estacao(admin):
    _, html = abrir(admin, cadastro.edicao())
    assert "Nenhuma estação cadastrada nesta edição." in html


def _consultas(client, edicao):
    with CaptureQueriesContext(connection) as capturadas:
        abrir(client, edicao)
    return len(capturadas)


def test_numero_de_consultas_nao_depende_do_tamanho(admin):
    pequena, grande = cadastro.edicao(nome="Pequena"), cadastro.edicao(nome="Grande")
    emitir(votacao.estacao(pequena), hora(29, 19, 0))
    for i in range(8):
        emitir(votacao.estacao(grande, nome=f"E{i}"), *[hora(29, 19, m) for m in range(10)])
    assert _consultas(admin, grande) == _consultas(admin, pequena)
