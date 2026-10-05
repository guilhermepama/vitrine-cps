"""Testes do cálculo do ranking (specs/04-resultados.md, critérios "Teste do
cálculo", desempate, banca pendente e pesos). Função pura: sem banco."""

from decimal import Decimal

import pytest

from resultados.calculo import (
    LinhaRanking,
    PesosInvalidos,
    ProjetoEntrada,
    TurmaEntrada,
    calcular_ranking,
)

D = Decimal
PB, PP = D("0.70"), D("0.30")


def turma(id_, *titulos, primeiro_id=None, nome=None):
    base = primeiro_id if primeiro_id is not None else id_ * 100
    projetos = [ProjetoEntrada(base + i, t) for i, t in enumerate(titulos)]
    return TurmaEntrada(id_, nome or f"Turma {id_}", projetos)


def calcular(turmas, votos=None, banca=None, pesos=(PB, PP), conferida=True):
    return calcular_ranking(turmas, votos or {}, banca or {}, pesos[0], pesos[1], conferida)


def por_titulo(ranking_turma):
    return {linha.titulo: linha for linha in ranking_turma.linhas}


# --- Normalização ------------------------------------------------------------


def test_votos_10_5_0_dao_p_1_meio_0():
    t = turma(1, "A", "B", "C")
    [r] = calcular([t], votos={100: 10, 101: 5, 102: 0}, banca={100: D(7), 101: D(7), 102: D(7)})
    linhas = por_titulo(r)
    assert [linhas[x].p for x in "ABC"] == [D(1), D("0.5"), D(0)]


def test_banca_8_7_6_da_b_1_meio_0():
    t = turma(1, "A", "B", "C")
    [r] = calcular([t], banca={100: D("8.0"), 101: D("7.0"), 102: D("6.0")})
    linhas = por_titulo(r)
    assert [linhas[x].b for x in "ABC"] == [D(1), D("0.5"), D(0)]
    assert [linhas[x].banca for x in "ABC"] == [D("8.0"), D("7.0"), D("6.0")]


def test_mesmos_votos_dao_p_1_e_mesma_banca_da_b_1():
    t = turma(1, "A", "B", "C")
    [r] = calcular([t], votos={100: 4, 101: 4, 102: 4}, banca={100: D("7.5"), 101: D("7.5"), 102: D("7.5")})
    assert all(linha.p == 1 and linha.b == 1 and linha.final == 1 for linha in r.linhas)


def test_todos_sem_voto_dao_p_1():
    [r] = calcular([turma(1, "A", "B")], banca={100: D(9), 101: D(5)})
    assert [linha.p for linha in r.linhas] == [D(1), D(1)]
    assert [linha.votos for linha in r.linhas] == [0, 0]


def test_normalizacao_local_a_turma():
    a = turma(1, "A1", "A2", "A3")
    b = turma(2, "B1", "B2", "B3")
    votos = {100: 100, 101: 50, 102: 0, 200: 4, 201: 2, 202: 0}
    banca = {pid: D(7) for pid in votos}
    ra, rb = calcular([a, b], votos=votos, banca=banca)
    assert [por_titulo(ra)[x].p for x in ("A1", "A2", "A3")] == [D(1), D("0.5"), D(0)]
    assert [por_titulo(rb)[x].p for x in ("B1", "B2", "B3")] == [D(1), D("0.5"), D(0)]


# --- Turmas com 1 ou 0 projetos ----------------------------------------------


def test_turma_com_1_projeto_e_nota_final_1_posicao_1():
    [r] = calcular([turma(1, "Único")], votos={100: 3}, banca={100: D("6.2")})
    [linha] = r.linhas
    assert (linha.p, linha.b, linha.final, linha.posicao, linha.empate) == (1, 1, 1, 1, False)
    assert r.banca_pendente is False


def test_turma_com_1_projeto_sem_nota_fica_pendente():
    [r] = calcular([turma(1, "Único")], votos={100: 3}, banca={})
    [linha] = r.linhas
    assert r.banca_pendente is True
    assert (linha.p, linha.b, linha.final, linha.posicao) == (1, None, None, None)


def test_turma_sem_projetos_nao_aparece():
    vazia = TurmaEntrada(9, "Vazia", [])
    res = calcular([vazia, turma(1, "A")], banca={100: D(5)})
    assert [r.turma_id for r in res] == [1]


def test_turmas_na_ordem_recebida():
    res = calcular([turma(2, "X"), turma(1, "Y")], banca={200: D(5), 100: D(5)})
    assert [r.turma_id for r in res] == [2, 1]


# --- Nota final e ordenação ---------------------------------------------------


def test_peso_70_30_banca_1_publico_0_fica_acima_de_banca_0_publico_1():
    t = turma(1, "Banca", "Público")
    [r] = calcular([t], votos={100: 0, 101: 50}, banca={100: D(9), 101: D(6)})
    primeiro, segundo = r.linhas
    assert (primeiro.titulo, primeiro.final, primeiro.posicao) == ("Banca", D("0.70"), 1)
    assert (segundo.titulo, segundo.final, segundo.posicao) == ("Público", D("0.30"), 2)


def test_final_com_pesos_da_edicao():
    t = turma(1, "A", "B", "C")
    [r] = calcular(
        [t], votos={100: 10, 101: 5, 102: 0}, banca={100: D(6), 101: D(8), 102: D(7)},
        pesos=(D("0.60"), D("0.40")),
    )
    linhas = por_titulo(r)
    # A: b=0, p=1 → 0,40 | B: b=1, p=0,5 → 0,80 | C: b=0,5, p=0 → 0,30
    assert [linhas[x].final for x in "ABC"] == [D("0.40"), D("0.80"), D("0.30")]
    assert [linha.titulo for linha in r.linhas] == ["B", "A", "C"]
    assert [linha.posicao for linha in r.linhas] == [1, 2, 3]


def test_sem_arredondamento_intermediario():
    # votos {3, 1, 0} → p de B = 1/3; banca {9, 7, 6} → b de B = 1/3.
    t = turma(1, "A", "B", "C")
    [r] = calcular([t], votos={100: 3, 101: 1, 102: 0}, banca={100: D(9), 101: D(7), 102: D(6)})
    b = por_titulo(r)["B"]
    terco = D(1) / D(3)
    assert b.p == terco and b.b == terco
    assert b.final == D(1) / D(3)  # 0,7·⅓ + 0,3·⅓, arredondado só na saída
    assert all(isinstance(v, Decimal) for linha in r.linhas for v in (linha.p, linha.b, linha.final))


# --- Desempate ----------------------------------------------------------------


def test_mesma_final_maior_banca_bruta_vence():
    # Votos {7, 0, 9} (faixa 9) e banca {6, 7, 9} (faixa 3):
    # "Z": 0,7·⅓ + 0 = 7/30;  "A": 0 + 0,3·7/9 = 7/30 → empate na final.
    t = turma(1, "A menor banca", "Z maior banca", "Topo")
    votos = {100: 7, 101: 0, 102: 9}
    banca = {100: D(6), 101: D(7), 102: D(9)}
    [r] = calcular([t], votos=votos, banca=banca)
    assert [linha.titulo for linha in r.linhas] == ["Topo", "Z maior banca", "A menor banca"]
    assert r.linhas[1].final == r.linhas[2].final
    assert [linha.posicao for linha in r.linhas] == [1, 2, 3]
    assert not any(linha.empate for linha in r.linhas)


def test_final_igual_so_no_valor_exato_desempata_pela_banca():
    # b de B = 0,3/2,8 = 3/28 (dízima) e p de A = 1/4: 0,7·3/28 = 0,3·1/4 = 0,075.
    # Em Decimal puro B daria 0,0749…97 < 0,0750 e A passaria à frente;
    # comparando o valor exato, empata e a banca maior (B) vence.
    t = turma(1, "A", "B", "C")
    votos = {100: 1, 101: 0, 102: 4}
    banca = {100: D("6.0"), 101: D("6.3"), 102: D("8.8")}
    [r] = calcular([t], votos=votos, banca=banca)
    assert [linha.titulo for linha in r.linhas] == ["C", "B", "A"]
    assert [linha.posicao for linha in r.linhas] == [1, 2, 3]
    assert not any(linha.empate for linha in r.linhas)


def test_mesma_final_e_mesma_banca_mais_votos_vence():
    # Com 70/30, final e banca iguais implicam votos iguais; o desempate por
    # votos só decide quando o peso do público é 0.
    # Títulos em ordem alfabética contrária à esperada, para o desempate por
    # votos não passar por acaso pela ordem alfabética.
    t = turma(1, "A menos votos", "B mais votos", "Outro")
    votos = {100: 2, 101: 5, 102: 9}
    banca = {100: D(8), 101: D(8), 102: D(6)}
    [r] = calcular([t], votos=votos, banca=banca, pesos=(D("1.00"), D("0.00")))
    assert [linha.titulo for linha in r.linhas] == ["B mais votos", "A menos votos", "Outro"]
    assert [linha.posicao for linha in r.linhas] == [1, 2, 3]
    assert not any(linha.empate for linha in r.linhas)


def test_empate_total_mesma_posicao_marca_e_ordem_alfabetica():
    t = turma(1, "Zebra", "Abelha", "Último")
    votos = {100: 5, 101: 5, 102: 0}
    banca = {100: D(8), 101: D(8), 102: D(6)}
    [r] = calcular([t], votos=votos, banca=banca)
    assert [linha.titulo for linha in r.linhas] == ["Abelha", "Zebra", "Último"]
    assert [linha.posicao for linha in r.linhas] == [1, 1, 3]
    assert [linha.empate for linha in r.linhas] == [True, True, False]


def test_empate_no_meio_pula_posicao():
    t = turma(1, "A", "B", "C", "D")
    votos = {100: 9, 101: 4, 102: 4, 103: 0}
    banca = {100: D(9), 101: D(7), 102: D(7), 103: D(5)}
    [r] = calcular([t], votos=votos, banca=banca)
    assert [linha.titulo for linha in r.linhas] == ["A", "B", "C", "D"]
    assert [linha.posicao for linha in r.linhas] == [1, 2, 2, 4]
    assert [linha.empate for linha in r.linhas] == [False, True, True, False]


def test_ordem_alfabetica_ignora_acento_e_caixa():
    t = turma(1, "barco", "Água", "Casa")
    [r] = calcular([t], banca={100: D(7), 101: D(7), 102: D(7)})
    assert [linha.titulo for linha in r.linhas] == ["Água", "barco", "Casa"]
    assert [linha.posicao for linha in r.linhas] == [1, 1, 1]


# --- Banca pendente -----------------------------------------------------------


def test_banca_nao_conferida_todas_as_turmas_pendentes_sem_final():
    a, b = turma(1, "A1", "A2"), turma(2, "B1", "B2")
    votos = {100: 10, 101: 0, 200: 3, 201: 6}
    banca = {pid: D(7) for pid in votos}
    res = calcular([a, b], votos=votos, banca=banca, conferida=False)
    assert all(r.banca_pendente for r in res)
    for r in res:
        for linha in r.linhas:
            assert (linha.banca, linha.b, linha.final, linha.posicao, linha.empate) == (None, None, None, None, False)
    assert [(linha.titulo, linha.votos, linha.p) for linha in res[1].linhas] == [("B2", 6, D(1)), ("B1", 3, D(0))]


def test_conferida_e_projeto_sem_nota_so_aquela_turma_fica_pendente():
    a, b = turma(1, "A1", "A2", "A3"), turma(2, "B1", "B2")
    votos = {100: 10, 101: 5, 102: 0, 200: 1, 201: 2}
    banca = {100: D(8), 101: D(7), 200: D(9), 201: D(6)}  # A3 sem nota
    ra, rb = calcular([a, b], votos=votos, banca=banca, conferida=True)
    assert ra.banca_pendente is True
    assert [linha.titulo for linha in ra.linhas] == ["A1", "A2", "A3"]  # A3 continua, com 0 votos
    assert all(linha.final is None and linha.b is None and linha.banca is None for linha in ra.linhas)
    assert [linha.p for linha in ra.linhas] == [D(1), D("0.5"), D(0)]
    assert rb.banca_pendente is False
    assert [(linha.titulo, linha.final, linha.posicao) for linha in rb.linhas] == [("B1", D("0.70"), 1), ("B2", D("0.30"), 2)]


def test_projeto_sem_voto_aparece_com_0_votos():
    t = turma(1, "Votado", "Sem voto")
    [r] = calcular([t], votos={100: 3}, banca={100: D(7), 101: D(7)})
    linha = por_titulo(r)["Sem voto"]
    assert (linha.votos, linha.p, linha.posicao) == (0, D(0), 2)


def test_pendente_ordena_por_votos_e_titulo():
    t = turma(1, "Zeta", "Alfa", "Meio")
    [r] = calcular([t], votos={100: 2, 101: 2, 102: 7}, conferida=False)
    assert [linha.titulo for linha in r.linhas] == ["Meio", "Alfa", "Zeta"]


# --- Pesos ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "pesos",
    [
        (None, None),
        (D("0.70"), None),
        (None, D("0.30")),
        (D("0.70"), D("0.20")),
        (D("0.80"), D("0.30")),
        (D("1.10"), D("-0.10")),
        (0.7, 0.3),  # float não entra no cálculo
        (D("NaN"), D("0.30")),
    ],
)
def test_pesos_ausentes_ou_que_nao_somam_1_levantam_erro(pesos):
    with pytest.raises(PesosInvalidos, match="Pesos da edição não configurados"):
        calcular([turma(1, "A")], banca={100: D(7)}, pesos=pesos)


def test_pesos_invalidos_barram_mesmo_com_banca_pendente():
    with pytest.raises(PesosInvalidos):
        calcular([turma(1, "A")], conferida=False, pesos=(None, None))


def test_pesos_invalidos_barram_mesmo_sem_turmas():
    with pytest.raises(PesosInvalidos):
        calcular([], pesos=(D("0.5"), D("0.4")))


def test_saida_e_dataclass_imutavel():
    [r] = calcular([turma(1, "A")], banca={100: D(7)})
    assert isinstance(r.linhas, tuple) and isinstance(r.linhas[0], LinhaRanking)
    with pytest.raises(AttributeError):
        r.linhas[0].final = D(0)


def test_nota_da_banca_como_o_postgres_entrega_nao_decide_o_desempate():
    """AVG(8, 9, 9) chega como 8.6666666666666667. Na conta exata, X (26/3) e
    Y (9) empatam no final (0,525) e Y vence pela banca maior; com o valor
    arredondado do Postgres, X ficaria à frente por 5,8e-18 (parecer do #52)."""
    from decimal import Decimal

    from resultados.calculo import ProjetoEntrada, TurmaEntrada, calcular_ranking

    turma = TurmaEntrada(id=1, nome="DSM", projetos=(
        ProjetoEntrada(1, "Alfa"), ProjetoEntrada(2, "Beta"), ProjetoEntrada(3, "A X"), ProjetoEntrada(4, "Z Y"),
    ))
    notas = {1: Decimal("6"), 2: Decimal("10"), 3: Decimal("8.6666666666666667"), 4: Decimal("9")}
    votos = {1: 36, 2: 0, 3: 7, 4: 0}
    ranking = calcular_ranking([turma], votos, notas, Decimal("0.70"), Decimal("0.30"), True)
    linhas = {linha.projeto_id: linha for linha in ranking[0].linhas}
    assert linhas[3].final == linhas[4].final
    assert linhas[4].posicao < linhas[3].posicao
    assert not linhas[3].empate and not linhas[4].empate
    assert linhas[3].banca == Decimal("8.6666666666666667")  # a tela mostra a nota como veio
