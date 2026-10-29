"""Planta fixa do prédio da Fatec Olímpia (spec 08, ADR-015).

As coordenadas vêm da planta desenhada no Figma (PLANTA_FATEC_OLIMPIA.fig):
o eixo x corre ao longo do corredor; o eixo y atravessa o prédio, com o lado A
(secretaria, biblioteca) em cima. A entrada do público é a passagem lateral,
na parede do lado A. Tudo em "unidades de mapa" — o SVG usa o mesmo sistema,
em paisagem. Em retrato o mapa gira 90° no sentido horário: o lado A vai para
a direita e a entrada fica na borda direita.

Mover um ponto é editar este arquivo (ADR-015). O conteúdo de cada ponto
(rótulo, atração, porta, projeto) vive em `mapa.Local`, ligado pelo `codigo`.
"""

from dataclasses import dataclass, replace

# --- Conversão da planta do Figma ----------------------------------------------
# O frame "Floorplan" do Figma vai de x=807 a 6899 e de y=790 a 2229 (px).
_X0, _Y0 = 807, 790
_ESCALA = 960 / 6092  # 960 unidades de mapa de comprimento

LARGURA = 960  # comprimento do prédio em unidades de mapa
ALTURA = round((2229 - 790) * _ESCALA)  # 227: largura do prédio
CORREDOR = (round((1351 - 790) * _ESCALA), round((1676 - 790) * _ESCALA))  # (88, 140)


def _x(px):
    return round((px - _X0) * _ESCALA, 1)


def _y(px):
    return round((px - _Y0) * _ESCALA, 1)


@dataclass(frozen=True)
class Ponto:
    codigo: str
    tipo: str  # estande | sala | servico | estacao | entrada
    x: float
    y: float
    w: float
    h: float
    fileira: str = ""
    ordem: int = 0
    rotulo: str = ""  # rótulo inicial; o admin pode trocar
    nome: str = ""  # nome inicial (serviços); o admin pode trocar

    @property
    def cx(self):
        return round(self.x + self.w / 2, 1)

    @property
    def cy(self):
        return round(self.y + self.h / 2, 1)

    def em_retrato(self):
        """Gira 90° no sentido horário: lado A à direita."""
        return replace(self, x=round(ALTURA - (self.y + self.h), 1), y=self.x, w=self.h, h=self.w)


TIPOS = ("estande", "sala", "servico", "passagem", "estacao", "entrada")

# --- Salas e serviços -------------------------------------------------------------
# Paredes divisórias lidas do Figma (x em px), da esquerda para a direita.
_PAREDES_A = (807, 1091, 1625, 1851, 2387, 2923, 3452, 3980, 4508, 4735, 5006, 5266, 5777, 6297, 6899)
_PAREDES_B = (807, 1091, 1307, 1856, 2389, 2922, 3452, 3980, 4501, 5027, 5550, 6078, 6480, 6899)

# (codigo, tipo, rotulo, nome), do lado esquerdo (fundo) para a entrada.
_SALAS_A = (
    ("wc-a", "servico", "WC", "Banheiro feminino"),
    ("sala-vip", "sala", "VIP", "Sala VIP · convidados"),
    ("apoio-a", "servico", "", "Apoio"),
    ("sala-a-07", "sala", "A7", ""),
    ("sala-a-06", "sala", "A6", ""),
    ("sala-a-05", "sala", "A5", ""),
    ("sala-a-04", "sala", "A4", ""),
    ("sala-a-03", "sala", "A3", ""),
    # Vão entre a A3 e a secretaria: corredor da entrada lateral, não é sala.
    ("entrada-lateral", "passagem", "Entrada", "Entrada lateral"),
    ("secretaria", "servico", "Secretaria", ""),
    ("ti", "servico", "TI", ""),
    ("biblioteca", "servico", "Biblioteca", ""),
    ("sala-a-02", "sala", "A2", ""),
    ("sala-a-01", "sala", "A1", ""),
)
# 13 vãos: WC, cozinha e refeitório no fundo, depois as salas B10 a B1 até a entrada.
_SALAS_B = (
    ("wc-b", "servico", "WC", "Banheiro masculino"),
    ("cozinha", "servico", "Cozinha", ""),
    ("refeitorio", "servico", "", "Refeitório"),
    ("sala-b-10", "sala", "B10", ""),
    ("sala-b-09", "sala", "B9", ""),
    ("sala-b-08", "sala", "B8", ""),
    ("sala-b-07", "sala", "B7", ""),
    ("sala-b-06", "sala", "B6", ""),
    ("sala-b-05", "sala", "B5", ""),
    ("sala-b-04", "sala", "B4", ""),
    ("sala-b-03", "sala", "B3", ""),
    ("sala-b-02", "sala", "B2", ""),
    ("sala-b-01", "sala", "B1", ""),
)

# --- Estandes, estações e entrada: posição final da montagem (29/10), em unidades de mapa ---
# (x, y) do canto superior esquerdo. Levantadas no dia, não derivadas do Figma.
ESTANDE_W, ESTANDE_H = 24, 17
_ESTANDES_A = (921, 887, 850, 814, 766, 726, 694, 664, 638, 544, 494, 459, 421, 381, 346)
_ESTANDES_B = (930, 895, 861, 818, 778, 741, 697, 662, 624, 559, 522, 481, 440, 388, 350, 312)
_Y_ESTANDES_A, _Y_ESTANDES_B = 90, 120

ESTACAO_R = 6
# (x, y, nome) do canto superior esquerdo do círculo (diâmetro 2·ESTACAO_R).
_ESTACOES = ((603, 72, "Entrada"), (845, 110, "Secretaria"), (718, 108, "Corredor · meio"), (466, 109, "Corredor · fundo"))

# Entrada do público: a passagem lateral, na parede do lado A (y < 0 = fora do prédio, em cima).
_ENTRADA = (583.2, -2, 35.8, 4)


def _salas(paredes, lado, y, h):
    pontos = []
    for i, (codigo, tipo, rotulo, nome) in enumerate(lado):
        x0, x1 = paredes[i], paredes[i + 1]
        pontos.append(Ponto(codigo, tipo, _x(x0), y, round(_x(x1) - _x(x0), 1), h, rotulo=rotulo, nome=nome))
    return pontos


def _estandes(xs, lado, fileira, y):
    # O código usa o lado fixo (a/b); só o rótulo muda com a letra escolhida.
    return [
        Ponto(f"{lado}{i:02d}", "estande", x, y, ESTANDE_W, ESTANDE_H, fileira=fileira, ordem=i, rotulo=f"{fileira}{i}")
        for i, x in enumerate(xs, start=1)
    ]


def pontos(fileiras=("A", "B")):
    """Todos os pontos da planta, em paisagem. `fileiras` troca só as letras dos estandes."""
    a, b = fileiras
    topo, base = CORREDOR
    lista = []
    lista += _salas(_PAREDES_A, _SALAS_A, 0, topo)
    lista += _salas(_PAREDES_B, _SALAS_B, base, ALTURA - base)
    lista += _estandes(_ESTANDES_A, "a", a, _Y_ESTANDES_A)
    lista += _estandes(_ESTANDES_B, "b", b, _Y_ESTANDES_B)
    for i, (x, y, nome) in enumerate(_ESTACOES, start=1):
        lista.append(Ponto(f"qr-{i:02d}", "estacao", x, y, ESTACAO_R * 2, ESTACAO_R * 2, ordem=i, rotulo="QR", nome=nome))
    lista.append(Ponto("entrada", "entrada", *_ENTRADA, rotulo="Entrada"))
    return lista


def por_codigo(fileiras=("A", "B")):
    return {p.codigo: p for p in pontos(fileiras)}
