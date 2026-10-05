"""Página do ranking por turma com participação (specs/04-resultados.md,
fatia 2), com dados reais do cadastro, da votação e da banca.

Critérios de aceite fechados aqui:
- Edição com `votacao_aberta_em` vazio → aviso, participação zerada
- Votação não encerrada → só o aviso, nenhum número de voto por projeto
- Só projetos `publicado` entram no ranking
- Projeto sem voto aparece com 0 votos
- `banca_conferida_em` vazio → todas as turmas com o aviso, nenhuma final
- Conferida e um projeto da turma A sem nota → turma A com aviso e sem
  final; turma B oficial
- Pesos ausentes ou que não somam 1 → "Pesos da edição não configurados"
- Zero tokens votantes → média "—"
- Nenhuma tela mostra ID de token ou IP
- Isolamento por edição: votos, tokens e visitantes de outra edição não
  entram no ranking nem na participação
- 5 turmas × 20 projetos executa o mesmo número de queries que 1 × 2
"""

import re
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from cadastro.models import Edicao, Projeto
from cadastro.tests import fabricas as cadastro
from resultados.tests import cenario
from votacao.models import Token
from votacao.tests import fabricas as votacao

pytestmark = pytest.mark.django_db

PENDENTE = "Nota da banca pendente — este não é o resultado oficial"


@pytest.fixture
def admin(client):
    client.force_login(cenario.usuario())
    return client


def abrir(client, edicao):
    resposta = client.get(reverse("resultados:ranking", args=[edicao.pk]))
    assert resposta.status_code == 200
    return resposta, resposta.content.decode()


def compacto(html):
    """HTML sem espaço entre as tags, para conferir uma linha inteira da tabela."""
    return re.sub(r">\s+<", "><", html)


def linhas(resposta, sigla):
    [turma] = [t for t in resposta.context["ranking"] if t.nome.startswith(sigla)]
    return turma, {linha.titulo: linha for linha in turma.linhas}


# --- Estados da votação --------------------------------------------------------


def test_votacao_nao_configurada_mostra_aviso_e_participacao_zerada(admin):
    ed, _ = cenario.edicao({"DSM": [("Agenda", 0, None)]}, estado="configurar")
    resposta, html = abrir(admin, ed)
    assert "Votação desta edição não foi configurada" in html
    assert resposta.context["ranking"] is None
    p = resposta.context["participacao"]
    assert (p["tokens_emitidos"], p["tokens_votantes"], p["total_votos"], p["visitantes"]) == (0, 0, 0, 0)
    assert p["media_por_token"] is None
    assert "Agenda" not in html


def test_votacao_nao_encerrada_so_aviso_sem_voto_por_projeto(admin):
    ed, _ = cenario.edicao({"DSM": [("Agenda", 3, 8), ("Horta", 4, 7)]}, estado="aberta")
    resposta, html = abrir(admin, ed)
    assert "Resultado disponível após o encerramento da votação" in html
    assert resposta.context["ranking"] is None
    assert "Agenda" not in html and "Horta" not in html
    # Os totais da edição continuam; a participação por turma só depois de
    # encerrar (parecer do #54): numa turma de um projeto seria o parcial dele.
    assert resposta.context["participacao"]["total_votos"] == 7
    assert resposta.context["participacao"]["turmas"] is None
    assert "<th>Turma</th>" not in html and "DSM —" not in html


def test_votacao_nao_configurada_sem_participacao_por_turma(admin):
    ed, _ = cenario.edicao({"DSM": [("Agenda", 0, None)]}, estado="configurar")
    resposta, html = abrir(admin, ed)
    assert resposta.context["participacao"]["turmas"] is None
    assert "<th>Turma</th>" not in html and "DSM —" not in html


# --- Ranking oficial -------------------------------------------------------------


def test_ranking_oficial_com_duas_casas_e_projeto_sem_voto(admin):
    ed, _ = cenario.edicao({"DSM": [("Agenda", 10, 8), ("Horta", 5, 7), ("Robô", 0, 6)]})
    resposta, html = abrir(admin, ed)
    turma, por_titulo = linhas(resposta, "DSM")
    assert not turma.banca_pendente
    assert [linha.titulo for linha in turma.linhas] == ["Agenda", "Horta", "Robô"]
    assert por_titulo["Robô"].votos == 0
    assert por_titulo["Horta"].p == Decimal("0.5") and por_titulo["Horta"].b == Decimal("0.5")
    assert [linha.final for linha in turma.linhas] == [1, Decimal("0.5"), 0]
    assert PENDENTE not in html
    # Linhas inteiras (posição, projeto, votos, banca, p, b, final, empate), 2 casas.
    tabela = compacto(html)
    assert '<td class="n">2º</td><td>Horta</td><td class="n">5</td><td class="n">7,00</td>' \
        '<td class="n">0,50</td><td class="n">0,50</td><td class="n">0,50</td><td></td>' in tabela
    assert '<td class="n">3º</td><td>Robô</td><td class="n">0</td><td class="n">6,00</td>' \
        '<td class="n">0,00</td><td class="n">0,00</td><td class="n">0,00</td><td></td>' in tabela


def test_empate_mesma_posicao_e_marca(admin):
    ed, _ = cenario.edicao({"DSM": [("Bote", 4, 7), ("Agenda", 4, 7), ("Caixa", 0, 5)]})
    resposta, html = abrir(admin, ed)
    turma, _ = linhas(resposta, "DSM")
    assert [(x.titulo, x.posicao, x.empate) for x in turma.linhas] == [
        ("Agenda", 1, True),
        ("Bote", 1, True),
        ("Caixa", 3, False),
    ]
    assert html.count("<td>empate</td>") == 2
    assert html.count("1º</td>") == 2 and "3º</td>" in html


def test_so_projetos_publicados_entram(admin):
    ed, projetos = cenario.edicao({"DSM": [("Agenda", 2, 8), ("Horta", 1, 7)]})
    rascunho = cadastro.projeto(projetos["Agenda"].turma, titulo="Rascunho Escondido")
    Projeto.objects.filter(pk=rascunho.pk).update(status=Projeto.Status.EM_REVISAO)
    resposta, html = abrir(admin, ed)
    _, por_titulo = linhas(resposta, "DSM")
    assert set(por_titulo) == {"Agenda", "Horta"}
    assert "Rascunho Escondido" not in html


def test_turma_sem_projeto_publicado_nao_aparece(admin):
    ed, _ = cenario.edicao({"DSM": [("Agenda", 2, 8)]})
    vazia = cadastro.turma(ed, cadastro.curso("GTUR"))
    cadastro.projeto(vazia, titulo="Não publicado")
    resposta, html = abrir(admin, ed)
    assert [t.nome[:3] for t in resposta.context["ranking"]] == ["DSM"]
    assert "GTUR" not in html


# --- Banca pendente e pesos ------------------------------------------------------


def test_banca_nao_conferida_todas_as_turmas_pendentes_sem_final(admin):
    ed, _ = cenario.edicao(
        {"DSM": [("Agenda", 3, 8), ("Horta", 1, 7)], "GTUR": [("Roteiro", 2, 9), ("Mapa", 0, 6)]},
        conferida=False,
    )
    resposta, html = abrir(admin, ed)
    assert all(t.banca_pendente for t in resposta.context["ranking"])
    assert all(linha.final is None for t in resposta.context["ranking"] for linha in t.linhas)
    assert html.count(PENDENTE) == 2
    assert "Final</th>" not in html and "Posição" not in html
    # A parte do público continua: votos e p.
    _, por_titulo = linhas(resposta, "DSM")
    assert (por_titulo["Agenda"].votos, por_titulo["Agenda"].p) == (3, 1)
    tabela = compacto(html)
    assert '<td>Agenda</td><td class="n">3</td><td class="n">1,00</td></tr>' in tabela
    assert '<td>Horta</td><td class="n">1</td><td class="n">0,00</td></tr>' in tabela


def test_conferida_com_projeto_sem_nota_so_aquela_turma_pendente(admin):
    ed, _ = cenario.edicao(
        {"DSM": [("Agenda", 3, 8), ("Horta", 1, None)], "GTUR": [("Roteiro", 2, 9), ("Mapa", 0, 6)]},
    )
    resposta, html = abrir(admin, ed)
    dsm, dsm_linhas = linhas(resposta, "DSM")
    gtur, _ = linhas(resposta, "GTUR")
    assert dsm.banca_pendente and not gtur.banca_pendente
    assert set(dsm_linhas) == {"Agenda", "Horta"}  # o projeto sem nota não sai do ranking
    assert all(linha.final is None and linha.b is None for linha in dsm.linhas)
    assert [linha.final for linha in gtur.linhas] == [1, 0]
    assert html.count(PENDENTE) == 1
    assert html.index(PENDENTE) < html.index("Roteiro")  # o aviso é da turma DSM


def test_pesos_que_nao_somam_1_mostram_erro_e_nao_calculam(admin):
    """O banco recusa pesos que não somam 1 (`pesos_somam_um`); o teste tira a
    constraint dentro da transação do teste (desfeita no fim) para simular
    um banco sem ela."""
    ed, _ = cenario.edicao({"DSM": [("Agenda", 3, 8), ("Horta", 1, 7)]})
    [constraint] = [c for c in Edicao._meta.constraints if c.name == "pesos_somam_um"]
    with connection.schema_editor() as editor:
        editor.remove_constraint(Edicao, constraint)
    Edicao.objects.filter(pk=ed.pk).update(peso_banca=Decimal("0.60"), peso_publico=Decimal("0.30"))
    resposta, html = abrir(admin, ed)
    assert "Pesos da edição não configurados" in html
    assert resposta.context["ranking"] is None
    assert "Agenda" not in html


# --- Participação ------------------------------------------------------------------


def test_participacao_agregada_da_edicao_e_por_turma(admin):
    ed, _ = cenario.edicao({"DSM": [("Agenda", 3, 8), ("Horta", 2, 7)], "GTUR": [("Roteiro", 1, 9)]})
    estacao = ed.estacoes.get()
    votacao.token(estacao)  # emitido e não usado
    votacao.visitante(ed)
    votacao.visitante(ed, nome="Outra Pessoa", email="outra@example.com")
    resposta, html = abrir(admin, ed)
    p = resposta.context["participacao"]
    # 3 tokens votaram (o 1º em 3 projetos, o 2º em 2, o 3º em 1): 6 votos.
    assert (p["tokens_emitidos"], p["tokens_votantes"], p["total_votos"], p["visitantes"]) == (4, 3, 6, 2)
    assert p["media_por_token"] == 2
    assert {t["nome"][:4]: (t["votos"], t["tokens"]) for t in p["turmas"]} == {"DSM ": (5, 3), "GTUR": (1, 1)}
    assert "2,00" in html
    # A tabela por turma aparece depois de encerrar, linha a linha.
    tabela = compacto(html)
    assert '<tr><td>DSM — 3º semestre</td><td class="n">5</td><td class="n">3</td></tr>' in tabela
    assert '<tr><td>GTUR — 3º semestre</td><td class="n">1</td><td class="n">1</td></tr>' in tabela


def test_zero_tokens_votantes_media_tracinho(admin):
    ed, _ = cenario.edicao({"DSM": [("Agenda", 0, 8)]})
    votacao.token(ed.estacoes.get())
    resposta, html = abrir(admin, ed)
    assert resposta.context["participacao"]["media_por_token"] is None
    assert "<td class=\"n\">—</td>" in html


def test_nenhum_id_de_token_nem_dado_de_visitante_na_tela(admin):
    ed, _ = cenario.edicao({"DSM": [("Agenda", 2, 8), ("Horta", 1, 7)]})
    votacao.visitante(ed, nome="Fulana Fictícia", email="fulana@example.com", telefone="17999990000")
    _, html = abrir(admin, ed)
    for token in Token.objects.all():
        assert str(token.pk) not in html and token.pk.hex not in html
    assert "Fulana" not in html and "fulana@example.com" not in html and "17999990000" not in html


# --- Isolamento por edição -----------------------------------------------------------


def test_outra_edicao_nao_entra_no_ranking_nem_na_participacao(admin):
    ed, projetos = cenario.edicao({"DSM": [("Agenda", 2, 8), ("Horta", 1, 7)]})
    ensaio, _ = cenario.edicao({"DSM": [("Do Ensaio", 9, 10)]}, nome="Ensaio 2026/2")
    votacao.visitante(ensaio)
    # Voto de token de estação do ensaio num projeto do evento: não conta.
    votacao.voto(votacao.token(ensaio.estacoes.get()), projetos["Horta"])
    resposta, html = abrir(admin, ed)
    p = resposta.context["participacao"]
    assert (p["tokens_emitidos"], p["tokens_votantes"], p["total_votos"], p["visitantes"]) == (2, 2, 3, 0)
    assert p["turmas"][0]["votos"] == 3
    _, por_titulo = linhas(resposta, "DSM")
    assert set(por_titulo) == {"Agenda", "Horta"} and por_titulo["Horta"].votos == 1
    assert "Do Ensaio" not in html


def test_token_do_evento_em_projeto_de_outra_edicao_nao_conta(admin):
    """Filtro "via projeto → turma → edição" (parecer do #54): um token do
    evento votando em projeto do ensaio (gravado direto, sem a cédula) não
    entra no evento nem no ensaio."""
    ed, _ = cenario.edicao({"DSM": [("Agenda", 2, 8), ("Horta", 1, 7)]})
    ensaio, ensaio_projetos = cenario.edicao({"DSM": [("Do Ensaio", 1, 10)]}, nome="Ensaio 2026/2")
    intruso = votacao.token(ed.estacoes.get())
    votacao.voto(intruso, ensaio_projetos["Do Ensaio"])
    resposta, _ = abrir(admin, ed)
    p = resposta.context["participacao"]
    assert (p["tokens_emitidos"], p["tokens_votantes"], p["total_votos"]) == (3, 2, 3)
    assert [t["votos"] for t in p["turmas"]] == [3]
    resposta, _ = abrir(admin, ensaio)
    p = resposta.context["participacao"]
    assert (p["tokens_votantes"], p["total_votos"]) == (1, 1)
    _, por_titulo = linhas(resposta, "DSM")
    assert por_titulo["Do Ensaio"].votos == 1


def test_titulo_do_projeto_sai_escapado(admin):
    ed, _ = cenario.edicao(
        {
            "DSM": [("<b>Robô & Cia</b>", 2, 8), ("Horta", 1, 7)],
            "GTUR": [("<i>Mapa</i>", 1, None), ("Roteiro", 0, 6)],  # turma pendente
        }
    )
    _, html = abrir(admin, ed)
    assert "<td>&lt;b&gt;Robô &amp; Cia&lt;/b&gt;</td>" in html
    assert "<td>&lt;i&gt;Mapa&lt;/i&gt;</td>" in html
    assert "<b>Robô" not in html and "<i>Mapa" not in html


# --- Número de consultas -------------------------------------------------------------


def _consultas(client, edicao):
    with CaptureQueriesContext(connection) as capturadas:
        resposta, _ = abrir(client, edicao)
    return len(capturadas), resposta


def test_numero_de_consultas_nao_depende_do_tamanho(admin):
    pequena, _ = cenario.edicao({"DSM": [("Agenda", 2, 8), ("Horta", 1, 7)]}, nome="Pequena")
    grande, _ = cenario.edicao(
        {
            f"C{t}": [(f"Projeto {t}-{i}", 1 + (i % 4), 5 + (i % 5)) for i in range(20)]
            for t in range(5)
        },
        nome="Grande",
    )
    n_pequena, r_pequena = _consultas(admin, pequena)
    n_grande, r_grande = _consultas(admin, grande)
    assert sum(len(t.linhas) for t in r_grande.context["ranking"]) == 100
    assert not any(t.banca_pendente for t in r_grande.context["ranking"])
    assert n_grande == n_pequena
