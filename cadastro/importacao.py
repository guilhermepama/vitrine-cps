"""Importação da lista das coordenações (specs/01-cadastro.md, "Importação da lista").

Duas fases: `analisar()` lê o CSV e decide o que fazer com cada linha, sem
gravar nada; `aplicar()` grava, numa transação, só se não houver nenhum erro.
O RA em claro nunca sai daqui: só o HMAC, e nenhuma mensagem o contém.
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field

from django.db import transaction

from cadastro.models import Curso, Projeto, Turma
from cadastro.seguranca import hash_ra

COLUNAS = {
    "curso": "Curso",
    "turma": "Turma",
    "periodo": "Período da turma",
    "titulo": "Nome do projeto",
    "representante": "Nome do representante",
    "ra": "RA do representante",
}
COLUNA_TURNO = "Turno"  # opcional (a planilha de 2026/2 foi sem ela)

PERIODOS = {"semestre": Turma.TipoPeriodo.SEMESTRE, "ano": Turma.TipoPeriodo.ANO, "modulo": Turma.TipoPeriodo.MODULO}
TURNOS = {"manha": Turma.Turno.MANHA, "tarde": Turma.Turno.TARDE, "noite": Turma.Turno.NOITE, "integral": Turma.Turno.INTEGRAL}


class ErroDeArquivo(Exception):
    """Problema no arquivo como um todo: o comando para antes de ler as linhas."""


@dataclass
class Linha:
    numero: int  # linha no CSV, contando o cabeçalho como 1
    resultado: str  # criado | atualizado | ignorado | erro
    motivo: str = ""
    titulo: str = ""
    # Para gravar (nunca o RA em claro)
    turma: Turma | None = None
    representante: str = ""
    ra_hmac: str = ""
    projeto: Projeto | None = None


@dataclass
class Relatorio:
    linhas: list[Linha] = field(default_factory=list)

    @property
    def tem_erro(self):
        return any(linha.resultado == "erro" for linha in self.linhas)

    def totais(self):
        contagem = {"criado": 0, "atualizado": 0, "ignorado": 0, "erro": 0}
        for linha in self.linhas:
            contagem[linha.resultado] += 1
        return contagem


def sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def normalizar_titulo(titulo):
    """Chave de comparação: sem espaços extras, sem acento, minúsculas."""
    return sem_acento(" ".join(titulo.split())).casefold()


def _chave_coluna(nome):
    return sem_acento(" ".join(nome.split())).casefold()


def ler_csv(conteudo):
    """Bytes do arquivo → (lista de dicts por coluna lógica, tem coluna de turno)."""
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ErroDeArquivo("O arquivo não está em UTF-8. No Excel, salve como \"CSV UTF-8 (delimitado por vírgulas)\".")
    try:
        dialeto = csv.Sniffer().sniff(texto.splitlines()[0] if texto else "", delimiters=";,")
        separador = dialeto.delimiter
    except csv.Error:
        separador = ";"
    leitor = csv.reader(io.StringIO(texto), delimiter=separador)
    cabecalho = next(leitor, None)
    if not cabecalho:
        raise ErroDeArquivo("O arquivo está vazio.")

    nomes = [_chave_coluna(c) for c in cabecalho]
    repetidas = sorted({c for c in cabecalho if nomes.count(_chave_coluna(c)) > 1})
    if repetidas:
        raise ErroDeArquivo(f"Coluna repetida no cabeçalho: {', '.join(repetidas)}.")
    posicao = {}
    faltando = []
    for chave, rotulo in COLUNAS.items():
        if _chave_coluna(rotulo) in nomes:
            posicao[chave] = nomes.index(_chave_coluna(rotulo))
        else:
            faltando.append(rotulo)
    if faltando:
        raise ErroDeArquivo(f"Faltam colunas no cabeçalho: {', '.join(faltando)}.")
    tem_turno = _chave_coluna(COLUNA_TURNO) in nomes
    if tem_turno:
        posicao["turno"] = nomes.index(_chave_coluna(COLUNA_TURNO))

    registros = []
    for celulas in leitor:
        registros.append({chave: (celulas[i].strip() if i < len(celulas) else "") for chave, i in posicao.items()})
    return registros, tem_turno


def _sigla(texto_curso):
    return re.split(r"\s+[—–-]\s+", texto_curso.strip(), maxsplit=1)[0].strip()


def _periodo(texto_turma, texto_periodo):
    """("3º semestre", "Semestre") → (3, "semestre"). Erro de linha → ValueError com o motivo."""
    tipo = PERIODOS.get(sem_acento(texto_periodo).casefold().strip())
    if tipo is None:
        raise ValueError("período da turma deve ser Semestre, Ano ou Módulo")
    achado = re.fullmatch(r"\s*(\d{1,2})\s*[ºª°o]?\.?\s*([a-zA-ZÀ-ÿ]*)\s*", texto_turma)
    if not achado:
        raise ValueError("turma deve ser no formato \"3º semestre\" ou \"2º ano\"")
    numero, escrito = int(achado.group(1)), sem_acento(achado.group(2)).casefold()
    if escrito and PERIODOS.get(escrito) != tipo:
        raise ValueError("período escrito em \"Turma\" diferente de \"Período da turma\"")
    return numero, tipo


def analisar(edicao, registros):
    """Decide o resultado de cada linha sem gravar nada."""
    relatorio = Relatorio()
    vistos_titulo = {}  # (turma_id, titulo normalizado) → linha
    vistos_ra = {}  # ra_hmac → linha
    projetos_da_turma = {}  # turma_id → {titulo normalizado: projeto}

    for indice, reg in enumerate(registros, start=2):
        titulo = " ".join(reg["titulo"].split())
        if not any(reg.values()):
            continue
        if titulo.upper().startswith("EXEMPLO"):
            relatorio.linhas.append(Linha(indice, "ignorado", "linha de exemplo", titulo))
            continue

        def erro(motivo):
            relatorio.linhas.append(Linha(indice, "erro", motivo, titulo))

        curso = Curso.objects.filter(sigla__iexact=_sigla(reg["curso"])).first() if reg["curso"] else None
        if curso is None:
            erro("curso inexistente")
            continue
        try:
            numero, tipo = _periodo(reg["turma"], reg["periodo"])
        except ValueError as motivo:
            erro(str(motivo))
            continue
        turmas = Turma.objects.filter(edicao=edicao, curso=curso, numero_periodo=numero, tipo_periodo=tipo)
        texto_turno = reg.get("turno", "")
        if texto_turno:
            turno = TURNOS.get(sem_acento(texto_turno).casefold())
            if turno is None:
                erro("turno deve ser manhã, tarde, noite ou integral")
                continue
            turmas = turmas.filter(turno=turno)
        turmas = list(turmas)
        if not turmas:
            erro("turma inexistente nesta edição")
            continue
        if len(turmas) > 1:
            erro("turma ambígua — informe o turno")
            continue
        turma = turmas[0]

        if not titulo or len(titulo) > 120:
            erro("nome do projeto vazio ou com mais de 120 caracteres")
            continue
        representante = " ".join(reg["representante"].split())
        if not representante or len(representante) > 120:
            erro("nome do representante vazio ou com mais de 120 caracteres")
            continue
        try:
            ra_hmac = hash_ra(reg["ra"])
        except ValueError:
            erro("RA inválido (só dígitos, de 5 a 20)")
            continue

        chave = (turma.pk, normalizar_titulo(titulo))
        if chave in vistos_titulo:
            erro(f"projeto repetido no arquivo (linha {vistos_titulo[chave]})")
            continue
        if ra_hmac in vistos_ra:
            erro(f"RA de outro projeto da edição (linha {vistos_ra[ra_hmac]})")
            continue
        vistos_titulo[chave] = indice
        vistos_ra[ra_hmac] = indice

        if turma.pk not in projetos_da_turma:
            projetos_da_turma[turma.pk] = {normalizar_titulo(p.titulo): p for p in turma.projetos.all()}
        existente = projetos_da_turma[turma.pk].get(chave[1])

        conflito = Projeto.objects.filter(ra_hmac=ra_hmac, turma__edicao=edicao)
        if existente:
            conflito = conflito.exclude(pk=existente.pk)
        if conflito.exists():
            erro("RA de outro projeto da edição")
            continue

        if existente is None:
            relatorio.linhas.append(Linha(indice, "criado", "", titulo, turma, representante, ra_hmac))
        elif existente.reivindicado_em:
            relatorio.linhas.append(Linha(indice, "ignorado", "já reivindicado", titulo))
        elif (existente.representante_nome, existente.ra_hmac) == (representante, ra_hmac):
            relatorio.linhas.append(Linha(indice, "ignorado", "sem alterações", titulo))
        else:
            relatorio.linhas.append(
                Linha(indice, "atualizado", "representante/RA", titulo, turma, representante, ra_hmac, existente)
            )
    return relatorio


def aplicar(relatorio):
    """Grava tudo ou nada. Chamar só sem erros."""
    if relatorio.tem_erro:
        raise ValueError("Relatório com erro: nada é gravado.")
    with transaction.atomic():
        for linha in relatorio.linhas:
            if linha.resultado == "criado":
                Projeto(
                    turma=linha.turma, titulo=linha.titulo, representante_nome=linha.representante, ra_hmac=linha.ra_hmac
                ).save()
            elif linha.resultado == "atualizado":
                linha.projeto.representante_nome = linha.representante
                linha.projeto.ra_hmac = linha.ra_hmac
                linha.projeto.save(update_fields=["representante_nome", "ra_hmac", "atualizado_em"])
