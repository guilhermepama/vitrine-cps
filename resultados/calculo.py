"""Cálculo do ranking por turma (specs/04-resultados.md, ADR-007).

Função pura: não toca no banco nem em HTTP. A view busca os dados (projetos
publicados por turma, votos, `banca.servicos.nota_banca_por_projeto`, pesos
e `Edicao.banca_conferida_em`) e chama `calcular_ranking`.

Regra (por turma, normalização local):
- `p = (votos - menor) / (maior - menor)`; se maior = menor, `p = 1`;
- `b` igual, sobre a nota de banca bruta;
- `final = peso_banca·b + peso_publico·p`;
- ordem: `final` desc, banca bruta desc, votos desc; empate em tudo →
  mesma posição, marca "empate", ordem alfabética e a posição seguinte
  pula os empatados (1, 1, 3).

Banca pendente: banca não conferida → todas as turmas; conferida mas algum
projeto da turma sem nota → só aquela turma. Turma pendente mostra só votos
e `p`, sem banca, `b`, nota final nem posição. O projeto nunca entra com
`b = 0` nem sai do ranking.

Números: tudo em `Decimal`, sem arredondamento (a tela mostra 2 casas). A
ordenação compara os valores exatos (`Fraction`), para que dois finais
matematicamente iguais não se separem por um resto de divisão (ex: 1/3) e o
desempate da banca/votos seja o que decide.
"""

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

UM = Decimal(1)


class PesosInvalidos(ValueError):
    """Pesos ausentes, não-Decimal, negativos ou que não somam 1."""

    mensagem = "Pesos da edição não configurados"

    def __init__(self):
        super().__init__(self.mensagem)


# --- Entrada -----------------------------------------------------------------


@dataclass(frozen=True)
class ProjetoEntrada:
    id: int
    titulo: str


@dataclass(frozen=True)
class TurmaEntrada:
    """Turma com os projetos que entram no ranking (já filtrados: publicados)."""

    id: int
    nome: str
    projetos: Sequence[ProjetoEntrada]


# --- Saída -------------------------------------------------------------------


@dataclass(frozen=True)
class LinhaRanking:
    """Uma linha da tabela da turma.

    Em turma com banca pendente, `banca`, `b`, `final` e `posicao` são None.
    `empate` é True quando o projeto divide a posição com outro (empate em
    final, banca bruta e votos).
    """

    projeto_id: int
    titulo: str
    votos: int
    p: Decimal
    banca: Decimal | None = None
    b: Decimal | None = None
    final: Decimal | None = None
    posicao: int | None = None
    empate: bool = False


@dataclass(frozen=True)
class RankingTurma:
    turma_id: int
    nome: str
    banca_pendente: bool
    linhas: tuple  # tuple[LinhaRanking, ...], na ordem de exibição


# --- Cálculo -----------------------------------------------------------------


def calcular_ranking(
    turmas: Sequence[TurmaEntrada],
    votos: Mapping[int, int],
    notas_banca: Mapping[int, Decimal],
    peso_banca: Decimal | None,
    peso_publico: Decimal | None,
    banca_conferida: bool,
) -> tuple:
    """Ranking de cada turma, na ordem recebida; turma sem projetos é omitida.

    - `votos`: {projeto_id: votos}; projeto ausente = 0 votos.
    - `notas_banca`: retorno de `nota_banca_por_projeto`; ausente = sem nota.
    - `banca_conferida`: `Edicao.banca_conferida_em is not None`.

    Levanta `PesosInvalidos` antes de calcular qualquer turma.
    """
    _validar_pesos(peso_banca, peso_publico)
    resultado = []
    for turma in turmas:
        if not turma.projetos:
            continue
        pendente = not banca_conferida or any(pr.id not in notas_banca for pr in turma.projetos)
        if pendente:
            linhas = _so_publico(turma.projetos, votos)
        else:
            linhas = _oficial(turma.projetos, votos, notas_banca, peso_banca, peso_publico)
        resultado.append(RankingTurma(turma.id, turma.nome, pendente, tuple(linhas)))
    return tuple(resultado)


def _validar_pesos(peso_banca, peso_publico):
    for peso in (peso_banca, peso_publico):
        if not isinstance(peso, Decimal) or not peso.is_finite() or peso < 0:
            raise PesosInvalidos()
    if peso_banca + peso_publico != UM:
        raise PesosInvalidos()


def _normalizar(valores):
    """Min-max exato: lista de Fraction em [0, 1]; maior = menor → 1."""
    menor, maior = min(valores), max(valores)
    if maior == menor:
        return [Fraction(1)] * len(valores)
    return [Fraction(v - menor) / Fraction(maior - menor) for v in valores]


def _decimal(fracao):
    return Decimal(fracao.numerator) / Decimal(fracao.denominator)


def _chave_titulo(titulo):
    """Ordem alfabética sem distinguir acento e caixa ("Água" antes de "Barco")."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", titulo) if not unicodedata.combining(c)
    )
    return (sem_acento.casefold(), titulo)


def _so_publico(projetos, votos):
    """Banca pendente: votos e `p`, ordenados por votos (desc) e título."""
    brutos = [votos.get(pr.id, 0) for pr in projetos]
    ps = _normalizar(brutos)
    linhas = [
        LinhaRanking(projeto_id=pr.id, titulo=pr.titulo, votos=v, p=_decimal(p))
        for pr, v, p in zip(projetos, brutos, ps)
    ]
    linhas.sort(key=lambda linha: (-linha.votos, _chave_titulo(linha.titulo), linha.projeto_id))
    return linhas


def _oficial(projetos, votos, notas_banca, peso_banca, peso_publico):
    brutos_v = [votos.get(pr.id, 0) for pr in projetos]
    brutos_b = [notas_banca[pr.id] for pr in projetos]
    ps = _normalizar(brutos_v)
    bs = _normalizar(brutos_b)
    pb, pp = Fraction(peso_banca), Fraction(peso_publico)

    itens = []
    for pr, v, nb, p, b in zip(projetos, brutos_v, brutos_b, ps, bs):
        final = pb * b + pp * p
        # Chave de empate total: final, banca bruta e votos.
        itens.append(((final, Fraction(nb), v), pr, v, nb, p, b, final))
    itens.sort(key=lambda it: (-it[0][0], -it[0][1], -it[0][2], _chave_titulo(it[1].titulo), it[1].id))

    contagem = {}
    for it in itens:
        contagem[it[0]] = contagem.get(it[0], 0) + 1

    linhas, posicao, chave_anterior = [], 0, None
    for indice, (chave, pr, v, nb, p, b, final) in enumerate(itens, start=1):
        if chave != chave_anterior:
            posicao, chave_anterior = indice, chave
        linhas.append(
            LinhaRanking(
                projeto_id=pr.id,
                titulo=pr.titulo,
                votos=v,
                p=_decimal(p),
                banca=nb,
                b=_decimal(b),
                final=_decimal(final),
                posicao=posicao,
                empate=contagem[chave] > 1,
            )
        )
    return linhas
