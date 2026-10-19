"""Cálculo do ranking por turma (specs/04-resultados.md, ADR-007).

Função pura: não toca no banco nem em HTTP. A view busca os dados (projetos
publicados por turma, avaliações do público, `banca.servicos.nota_banca_por_projeto`,
pesos e `Edicao.banca_conferida_em`) e chama `calcular_ranking`.

Público (ADR-012): cada avaliação dá notas de 0 a 5 em três critérios; a nota
da avaliação é a média das três. O valor do público de um projeto é a média
bayesiana `(C·m + soma das notas) / (C + nº de avaliações)`, com `m` = média
de todas as avaliações da turma e `C = AVALIACOES_DE_REFERENCIA` — ver
`publico_por_media_bayesiana`. `calcular_ranking` recebe o valor pronto
(`Publico`); um `int` ainda é aceito como contagem de votos (regra anterior,
usada pela view até o `Voto` ter as notas — spec 03).

Regra (por turma, normalização local):
- `p = (público - menor) / (maior - menor)`; se maior = menor, `p = 1`;
- `b` igual, sobre a nota de banca bruta;
- `final = peso_banca·b + peso_publico·p`;
- ordem: `final` desc, banca bruta desc, mais avaliações; empate em tudo →
  mesma posição, marca "empate", ordem alfabética e a posição seguinte
  pula os empatados (1, 1, 3).

Banca pendente: banca não conferida → todas as turmas; conferida mas algum
projeto da turma sem nota → só aquela turma. Turma pendente mostra só o
público e `p`, sem banca, `b`, nota final nem posição. O projeto nunca entra com
`b = 0` nem sai do ranking.

Números: o cálculo é todo em `Fraction` (exato, sem arredondamento); só a
saída (`LinhaRanking`) vira `Decimal`, e a tela mostra 2 casas. A ordenação
compara os valores exatos, para que dois finais matematicamente iguais não se
separem por um resto de divisão (ex: 1/3) e o desempate da banca/votos seja o
que decide. Os pesos da edição chegam como `Decimal` e viram `Fraction`.
"""

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

UM = Decimal(1)

# ADR-012: três critérios por avaliação (impacto social, inovação, impacto
# ambiental), cada um de 0 a 5; C = avaliações "na média da turma" com que
# todo projeto começa.
CRITERIOS = 3
NOTA_MAXIMA = 5
AVALIACOES_DE_REFERENCIA = 10


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


@dataclass(frozen=True)
class NotasDoProjeto:
    """Avaliações do público de um projeto, já somadas pelo banco.

    `pontos` é a soma das três notas de todas as avaliações (0 a 15 por
    avaliação), o que basta para a média de cada avaliação sem arredondar.
    """

    avaliacoes: int
    pontos: int


@dataclass(frozen=True)
class Publico:
    """Parte do público de um projeto, pronta para o ranking.

    `valor` é o número que vai para a normalização; `avaliacoes` desempata e
    aparece na tabela; `media` (média simples das notas) é só exibição.
    """

    valor: Fraction
    avaliacoes: int
    media: Fraction | None = None


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
    votos: int  # nº de avaliações (ou de votos, na regra anterior)
    p: Decimal
    publico: Decimal | None = None  # valor do público antes da normalização
    media: Decimal | None = None  # média simples das notas; None sem avaliação
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


def publico_por_media_bayesiana(
    turmas: Sequence[TurmaEntrada],
    notas: Mapping[int, NotasDoProjeto],
    referencia: int = AVALIACOES_DE_REFERENCIA,
) -> dict:
    """{projeto_id: Publico} pela média bayesiana do ADR-012, turma a turma.

    - `m` é a média de todas as avaliações da turma (normalização local).
    - Projeto sem avaliação fica com `m` (só as avaliações de referência).
    - Turma sem nenhuma avaliação: valor 0 para todos (a normalização dá
      `p = 1` a todos, como na regra de valores iguais).
    - Uma avaliação abaixo do **valor atual** do projeto baixa o valor (com
      `m` fixo). Como `m` inclui a própria avaliação, com poucas avaliações
      na turma uma nota abaixo de `m` — mas acima do valor do projeto —
      pode subir um projeto fraco (limite (3) do ADR-012; spec 04).

    Levanta `ValueError` para soma impossível (o banco já barra notas fora
    de 0–5; aqui é a última conferência antes do resultado oficial).
    """
    if not isinstance(referencia, int) or referencia < 1:
        raise ValueError("referência da média bayesiana inválida")
    resultado = {}
    for turma in turmas:
        dados = {pr.id: notas.get(pr.id, NotasDoProjeto(0, 0)) for pr in turma.projetos}
        for d in dados.values():
            if d.avaliacoes < 0 or not 0 <= d.pontos <= CRITERIOS * NOTA_MAXIMA * d.avaliacoes:
                raise ValueError("soma de notas impossível para o número de avaliações")
        total = sum(d.avaliacoes for d in dados.values())
        if total == 0:
            resultado.update({pid: Publico(Fraction(0), 0) for pid in dados})
            continue
        m = Fraction(sum(d.pontos for d in dados.values()), CRITERIOS * total)
        for pid, d in dados.items():
            soma = Fraction(d.pontos, CRITERIOS)  # soma das notas das avaliações
            valor = (referencia * m + soma) / (referencia + d.avaliacoes)
            media = soma / d.avaliacoes if d.avaliacoes else None
            resultado[pid] = Publico(valor, d.avaliacoes, media)
    return resultado


def calcular_ranking(
    turmas: Sequence[TurmaEntrada],
    publico: Mapping[int, "Publico | int"],
    notas_banca: Mapping[int, Decimal],
    peso_banca: Decimal | None,
    peso_publico: Decimal | None,
    banca_conferida: bool,
) -> tuple:
    """Ranking de cada turma, na ordem recebida; turma sem projetos é omitida.

    - `publico`: {projeto_id: Publico} (ADR-012) ou {projeto_id: votos}
      (int, regra anterior); projeto ausente = 0.
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
        dados = [_publico(publico.get(pr.id)) for pr in turma.projetos]
        if pendente:
            linhas = _so_publico(turma.projetos, dados)
        else:
            linhas = _oficial(turma.projetos, dados, notas_banca, peso_banca, peso_publico)
        resultado.append(RankingTurma(turma.id, turma.nome, pendente, tuple(linhas)))
    return tuple(resultado)


def _publico(valor):
    """Publico de um projeto; `int` = contagem de votos (regra anterior)."""
    if valor is None:
        return Publico(Fraction(0), 0)
    if isinstance(valor, Publico):
        return valor
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
        raise TypeError("público precisa ser Publico ou contagem (int >= 0)")
    return Publico(Fraction(valor), valor)


def _decimal_ou_none(fracao):
    return None if fracao is None else _decimal(fracao)


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


# A nota da banca vem do AVG do Postgres, já arredondada na 16ª-20ª casa
# (8, 9, 9 → 8.6666666666666667). As notas têm uma casa decimal, então a média
# exata é uma fração de denominador pequeno: limit_denominator a recupera, e o
# resto do arredondamento não decide desempate (parecer do #52).
DENOMINADOR_MAXIMO = 10**6


def _nota_exata(nota):
    return Fraction(nota).limit_denominator(DENOMINADOR_MAXIMO)


def _decimal(fracao):
    return Decimal(fracao.numerator) / Decimal(fracao.denominator)


def chave_alfabetica(titulo):
    """Ordem alfabética sem distinguir acento e caixa ("Água" antes de "Barco")."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", titulo) if not unicodedata.combining(c)
    )
    return (sem_acento.casefold(), titulo)


def _so_publico(projetos, dados):
    """Banca pendente: público e `p`, ordenados pelo público (desc), avaliações e título."""
    ps = _normalizar([d.valor for d in dados])
    linhas = [
        LinhaRanking(
            projeto_id=pr.id,
            titulo=pr.titulo,
            votos=d.avaliacoes,
            p=_decimal(p),
            publico=_decimal(d.valor),
            media=_decimal_ou_none(d.media),
        )
        for pr, d, p in zip(projetos, dados, ps)
    ]
    valores = {pr.id: d.valor for pr, d in zip(projetos, dados)}
    linhas.sort(
        key=lambda linha: (-valores[linha.projeto_id], -linha.votos, chave_alfabetica(linha.titulo), linha.projeto_id)
    )
    return linhas


def _oficial(projetos, dados, notas_banca, peso_banca, peso_publico):
    brutos_b = [_nota_exata(notas_banca[pr.id]) for pr in projetos]
    ps = _normalizar([d.valor for d in dados])
    bs = _normalizar(brutos_b)
    pb, pp = Fraction(peso_banca), Fraction(peso_publico)

    itens = []
    for pr, d, nb, p, b in zip(projetos, dados, brutos_b, ps, bs):
        final = pb * b + pp * p
        # Chave de empate total: final, banca bruta (exata) e nº de avaliações.
        itens.append(((final, nb, d.avaliacoes), pr, d, notas_banca[pr.id], p, b, final))
    itens.sort(key=lambda it: (-it[0][0], -it[0][1], -it[0][2], chave_alfabetica(it[1].titulo), it[1].id))

    contagem = {}
    for it in itens:
        contagem[it[0]] = contagem.get(it[0], 0) + 1

    linhas, posicao, chave_anterior = [], 0, None
    for indice, (chave, pr, d, nb, p, b, final) in enumerate(itens, start=1):
        if chave != chave_anterior:
            posicao, chave_anterior = indice, chave
        linhas.append(
            LinhaRanking(
                projeto_id=pr.id,
                titulo=pr.titulo,
                votos=d.avaliacoes,
                p=_decimal(p),
                publico=_decimal(d.valor),
                media=_decimal_ou_none(d.media),
                banca=nb,
                b=_decimal(b),
                final=_decimal(final),
                posicao=posicao,
                empate=contagem[chave] > 1,
            )
        )
    return linhas
