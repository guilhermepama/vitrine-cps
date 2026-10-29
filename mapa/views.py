"""Página pública do mapa do evento (spec 08). Só leitura; nenhum caminho de voto (G8)."""

import re

from django.shortcuts import render

from cadastro.models import Edicao, Projeto
from mapa import planta
from mapa.models import Local

_CODIGO = re.compile(r"[a-z0-9-]{1,20}")
_NOME_MAX = 18  # caracteres por linha de nome dentro da sala


def _quebrar(nome):
    """Nome da atração em até duas linhas curtas para caber na sala."""
    palavras = nome.split()
    linhas, atual = [], ""
    for p in palavras:
        if atual and len(atual) + 1 + len(p) > _NOME_MAX:
            linhas.append(atual)
            atual = p
        else:
            atual = f"{atual} {p}".strip()
    if atual:
        linhas.append(atual)
    if len(linhas) > 2:
        linhas = linhas[:2]
        linhas[1] = linhas[1][: _NOME_MAX - 1] + "…"
    return linhas


def _elemento(ponto, local, aqui):
    projeto = local.projeto if local else None
    publicado = projeto is not None and projeto.status == Projeto.Status.PUBLICADO
    aberta = local.aberta if local else True
    nome = (local.nome if local else ponto.nome) if aberta else ""
    if ponto.tipo == "estande":
        # Estande sem projeto pode ter expositor com nome (ex.: Secretaria de Turismo);
        # com projeto, quem aparece é o projeto, na lista de estandes.
        nome = local.nome if local is not None and projeto is None else ""
    # Serviço só vira atração quando o admin trocou o nome padrão (WC continua WC).
    atracao = bool(nome) and (ponto.tipo in ("sala", "estande") or (local is not None and local.nome != ponto.nome))
    return {
        "atracao": atracao,
        "codigo": ponto.codigo,
        "tipo": ponto.tipo,
        "rotulo": (local.rotulo if local else ponto.rotulo),
        "nome": nome,
        "linhas": _quebrar(nome) if ponto.tipo in ("sala", "servico") else [],  # passagem: só o rótulo
        "aberta": aberta,
        "ocupado": projeto is not None or (ponto.tipo == "estande" and bool(nome)),
        "publicado": publicado,
        "aqui": ponto.codigo == aqui,
        "paisagem": ponto,
        "retrato": ponto.em_retrato(),
        "local": local,
    }


def mapa(request):
    aqui = request.GET.get("aqui", "")
    if not _CODIGO.fullmatch(aqui):
        aqui = ""  # G12: valor fora do padrão vira "sem marcação", sem erro

    edicao = Edicao.objects.filter(ativa=True).first()
    locais = {}
    if edicao is not None:
        locais = {
            local.codigo: local
            for local in Local.objects.filter(edicao=edicao).select_related("projeto__turma__curso")
        }

    elementos = [_elemento(p, locais.get(p.codigo), aqui) for p in planta.pontos()]
    por_codigo = {e["codigo"]: e for e in elementos}
    alvo = por_codigo.get(aqui)
    if alvo is None or alvo["tipo"] != "estacao":
        alvo = None  # "você está aqui" só em estação de QR; outro ponto vira ausente
    estandes = sorted(
        (e for e in elementos if e["tipo"] == "estande" and e["publicado"]),
        key=lambda e: (e["paisagem"].fileira, e["paisagem"].ordem),
    )
    salas = [e for e in elementos if e["atracao"] and e["local"]]
    fileiras = sorted({e["paisagem"].fileira for e in elementos if e["tipo"] == "estande"})

    return render(
        request,
        "mapa/mapa.html",
        {
            "edicao": edicao,
            "estandes": estandes,
            "salas": salas,
            "fileiras": fileiras,
            "em_montagem": not locais,
            "aqui": alvo,
            "vistas": {"paisagem": _vista(elementos, "paisagem"), "retrato": _vista(elementos, "retrato")},
        },
    )


_MARGEM = 24  # espaço em volta do prédio para o texto "ENTRADA", em qualquer lado


def _texto_da_entrada(ponto, lado_predio_w, lado_predio_h):
    """Posição, rotação e seta do texto "ENTRADA", do lado de fora do prédio, apontando para dentro."""
    cx, cy = ponto.cx, ponto.cy
    if cy <= 0:
        return {"x": _n(cx), "y": _n(ponto.y - 10), "rotacao": "", "seta": "▼"}
    if cy >= lado_predio_h:
        return {"x": _n(cx), "y": _n(ponto.y + ponto.h + 10), "rotacao": "", "seta": "▲"}
    if cx >= lado_predio_w:
        return {"x": _n(ponto.x + ponto.w + 10), "y": _n(cy), "rotacao": "-90", "seta": "▲"}
    return {"x": _n(ponto.x - 10), "y": _n(cy), "rotacao": "90", "seta": "▲"}


def _vista(elementos, orientacao):
    """Elementos com a geometria da orientação pedida, mais o quadro, o corredor e a entrada."""
    largura, altura = planta.LARGURA, planta.ALTURA
    topo, base = planta.CORREDOR
    entrada_ponto = next(e[orientacao] for e in elementos if e["tipo"] == "entrada")
    if orientacao == "paisagem":
        predio = {"w": _n(largura), "h": _n(altura)}
        corredor = {"x": "0", "y": _n(topo), "w": _n(largura), "h": _n(base - topo)}
        entrada = _texto_da_entrada(entrada_ponto, largura, altura)
        viewbox = f"{-_MARGEM} {-_MARGEM} {largura + 2 * _MARGEM} {altura + 2 * _MARGEM}"
    else:
        predio = {"w": _n(altura), "h": _n(largura)}
        corredor = {"x": _n(altura - base), "y": "0", "w": _n(base - topo), "h": _n(largura)}
        entrada = _texto_da_entrada(entrada_ponto, altura, largura)
        viewbox = f"{-_MARGEM} {-_MARGEM} {altura + 2 * _MARGEM} {largura + 2 * _MARGEM}"
    return {
        "orientacao": orientacao,
        "viewbox": viewbox,
        "predio": predio,
        "corredor": corredor,
        "entrada": entrada,
        "raio_estacao": _n(planta.ESTACAO_R),
        "raio_aqui": _n(planta.ESTACAO_R + 7),
        "raio_anel": _n(planta.ESTACAO_R + 4),
        "itens": [{**e, "g": _geometria(e[orientacao], e)} for e in elementos],
    }


def _n(valor):
    """Número para atributo SVG: sem vírgula decimal do pt-BR (USE_L10N) e sem zeros à toa."""
    return f"{valor:g}"


def _geometria(ponto, e):
    mostra_nome = bool(e["linhas"]) and ponto.w >= 60
    return {
        "x": _n(ponto.x),
        "y": _n(ponto.y),
        "w": _n(ponto.w),
        "h": _n(ponto.h),
        "cx": _n(ponto.cx),
        "cy": _n(ponto.cy),
        "mostra_nome": mostra_nome,
        "rotulo_y": _n(ponto.cy - 8 if mostra_nome else ponto.cy),
        "nome_y": _n(ponto.cy + 8),
    }
