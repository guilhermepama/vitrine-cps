"""Média bayesiana do público (ADR-012; specs/04-resultados.md, "Público").

Função pura: sem banco. Os casos com número são os da decisão do coordenador
(16/10): a soma foi descartada porque uma nota baixa aumentava a pontuação, e
a média simples porque 1 avaliação 5 vencia 60 de média 4,8.
"""

from decimal import Decimal
from fractions import Fraction

import pytest

from resultados.calculo import (
    AVALIACOES_DE_REFERENCIA,
    NotasDoProjeto,
    ProjetoEntrada,
    Publico,
    TurmaEntrada,
    calcular_ranking,
    publico_por_media_bayesiana,
)

D, F = Decimal, Fraction
PB, PP = D("0.70"), D("0.30")


def turma(id_, *titulos):
    return TurmaEntrada(id_, f"Turma {id_}", [ProjetoEntrada(id_ * 100 + i, t) for i, t in enumerate(titulos)])


def avaliacoes(*notas):
    """NotasDoProjeto a partir de avaliações (s, i, a) — uma tupla por avaliação."""
    return NotasDoProjeto(len(notas), sum(sum(n) for n in notas))


def iguais(nota, quantas):
    """`quantas` avaliações com as três notas iguais a `nota`."""
    return avaliacoes(*[(nota, nota, nota)] * quantas)


def test_referencia_e_10():
    assert AVALIACOES_DE_REFERENCIA == 10


def test_formula_com_media_da_turma():
    # Turma: A com 2 avaliações (5,5,5) e (3,3,3); B com 1 avaliação (1,1,1).
    t = turma(1, "A", "B")
    pub = publico_por_media_bayesiana([t], {100: avaliacoes((5, 5, 5), (3, 3, 3)), 101: iguais(1, 1)})
    m = F(5 + 3 + 1, 3)  # média das 3 avaliações da turma = 3
    assert pub[100] == Publico((10 * m + 8) / 12, 2, F(4))
    assert pub[101] == Publico((10 * m + 1) / 11, 1, F(1))


def test_nota_da_avaliacao_e_a_media_dos_tres_criterios():
    t = turma(1, "A")
    pub = publico_por_media_bayesiana([t], {100: avaliacoes((5, 4, 0))})
    assert pub[100].media == F(9, 3)


SESSENTA_DE_4_8 = NotasDoProjeto(60, 3 * (48 * 5 + 12 * 4))  # 48 notas 5 e 12 notas 4: 60·4,8 = 288


def test_uma_avaliacao_5_nao_vence_60_de_4_8():
    # Turma realista: um terceiro projeto com 30 avaliações nota 3 põe a média da turma em ~4,2.
    t = turma(1, "Uma nota", "Sessenta", "Outro")
    pub = publico_por_media_bayesiana([t], {100: iguais(5, 1), 101: SESSENTA_DE_4_8, 102: iguais(3, 30)})
    assert pub[101].valor > pub[100].valor
    assert pub[100].media > pub[101].media  # na média simples, a de 1 avaliação ganharia


def test_limite_conhecido_turma_inteira_perto_de_4_8():
    """Limite do método, registrado no ADR-012: se a média da turma já é ~4,8,
    o projeto de 60 avaliações está *abaixo* dela e uma avaliação 5 fica um
    pouco acima (4,82 × 4,80). Com a média da turma menor, o de 60 vence."""
    t = turma(1, "Uma nota", "Sessenta")
    pub = publico_por_media_bayesiana([t], {100: iguais(5, 1), 101: SESSENTA_DE_4_8})
    assert pub[100].valor > pub[101].valor
    assert pub[100].valor - pub[101].valor < F(1, 40)  # diferença pequena: menos de 0,025


def test_quarenta_notas_2_nao_vencem_quinze_notas_5():
    t = turma(1, "Quarenta", "Quinze")
    pub = publico_por_media_bayesiana([t], {100: iguais(2, 40), 101: iguais(5, 15)})
    assert pub[101].valor > pub[100].valor  # na soma, 80 venceria 75


def test_nota_abaixo_da_media_baixa_o_valor():
    t = turma(1, "A", "B")
    antes = publico_por_media_bayesiana([t], {100: iguais(4, 5), 101: iguais(4, 5)})[100].valor
    depois = publico_por_media_bayesiana([t], {100: avaliacoes(*[(4, 4, 4)] * 5, (0, 0, 0)), 101: iguais(4, 5)})[100]
    assert depois.valor < antes and depois.avaliacoes == 6


def test_projeto_sem_avaliacao_fica_com_a_media_da_turma():
    t = turma(1, "A", "Sem")
    pub = publico_por_media_bayesiana([t], {100: iguais(4, 6)})
    assert pub[101] == Publico(F(4), 0, None)


def test_turma_sem_avaliacoes_da_p_1_para_todos():
    t = turma(1, "A", "B")
    pub = publico_por_media_bayesiana([t], {})
    assert pub[100] == pub[101] == Publico(F(0), 0, None)
    [r] = calcular_ranking([t], pub, {100: D(8), 101: D(6)}, PB, PP, True)
    assert all(linha.p == 1 for linha in r.linhas)


def test_media_da_turma_e_local():
    a, b = turma(1, "A1", "A2"), turma(2, "B1", "B2")
    pub = publico_por_media_bayesiana([a, b], {100: iguais(5, 3), 200: iguais(1, 3)})
    assert pub[101].valor == F(5)  # projeto sem avaliação da turma A fica com 5, não com a média geral
    assert pub[201].valor == F(1)


def test_notas_zero_sao_notas():
    t = turma(1, "A", "B")
    pub = publico_por_media_bayesiana([t], {100: iguais(0, 4), 101: iguais(3, 4)})
    assert pub[100].media == 0 and pub[100].avaliacoes == 4 and pub[100].valor < pub[101].valor


@pytest.mark.parametrize("notas", [NotasDoProjeto(1, 16), NotasDoProjeto(2, -1), NotasDoProjeto(-1, 0), NotasDoProjeto(0, 3)])
def test_soma_impossivel_e_recusada(notas):
    with pytest.raises(ValueError):
        publico_por_media_bayesiana([turma(1, "A")], {100: notas})


@pytest.mark.parametrize("referencia", [0, -5, 2.5])
def test_referencia_invalida_e_recusada(referencia):
    with pytest.raises(ValueError):
        publico_por_media_bayesiana([turma(1, "A")], {}, referencia)


def test_ranking_usa_o_valor_bayesiano_e_mostra_avaliacoes_e_media():
    t = turma(1, "Uma nota", "Sessenta", "Outro")
    pub = publico_por_media_bayesiana([t], {100: iguais(5, 1), 101: SESSENTA_DE_4_8, 102: iguais(3, 30)})
    [r] = calcular_ranking([t], pub, {100: D(7), 101: D(7), 102: D(7)}, PB, PP, True)
    por = {linha.titulo: linha for linha in r.linhas}
    assert (por["Sessenta"].posicao, por["Sessenta"].p, por["Sessenta"].votos) == (1, 1, 60)
    assert por["Sessenta"].media == D("4.8") and por["Uma nota"].media == 5 and por["Outro"].p == 0
    assert por["Uma nota"].posicao == 2
    assert por["Sessenta"].publico == D(pub[101].valor.numerator) / D(pub[101].valor.denominator)


def test_banca_pendente_ordena_pelo_valor_bayesiano():
    t = turma(1, "Uma nota", "Sessenta", "Outro")
    pub = publico_por_media_bayesiana([t], {100: iguais(5, 1), 101: SESSENTA_DE_4_8, 102: iguais(3, 30)})
    [r] = calcular_ranking([t], pub, {}, PB, PP, banca_conferida=False)
    assert r.banca_pendente and [linha.titulo for linha in r.linhas] == ["Sessenta", "Uma nota", "Outro"]
    assert all(linha.final is None for linha in r.linhas)


def test_empate_em_final_e_banca_desempata_por_mais_avaliacoes():
    # Mesmo valor bayesiano (todas as notas = média da turma) com nº de avaliações diferente.
    t = turma(1, "Poucas", "Muitas", "Baixa")
    pub = publico_por_media_bayesiana([t], {100: iguais(4, 2), 101: iguais(4, 8), 102: avaliacoes((4, 4, 4), (4, 4, 4))})
    pub[102] = Publico(F(0), 1)  # força um mínimo diferente para a normalização não dar 1 a todos
    [r] = calcular_ranking([t], pub, {100: D(7), 101: D(7), 102: D(7)}, PB, PP, True)
    por = {linha.titulo: linha for linha in r.linhas}
    assert por["Poucas"].final == por["Muitas"].final
    assert por["Muitas"].posicao == 1 and por["Poucas"].posicao == 2 and not por["Muitas"].empate


def test_contagem_int_continua_aceita_como_regra_anterior():
    t = turma(1, "A", "B")
    [r] = calcular_ranking([t], {100: 10, 101: 0}, {100: D(7), 101: D(7)}, PB, PP, True)
    por = {linha.titulo: linha for linha in r.linhas}
    assert (por["A"].votos, por["A"].p, por["A"].publico, por["A"].media) == (10, 1, 10, None)


@pytest.mark.parametrize("ruim", [-1, True, 2.5, "3"])
def test_publico_invalido_e_recusado(ruim):
    with pytest.raises(TypeError):
        calcular_ranking([turma(1, "A")], {100: ruim}, {100: D(7)}, PB, PP, True)
