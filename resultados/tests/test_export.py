"""Export de visitantes (specs/04-resultados.md, fatia 3). Só dados fictícios.

Critérios de aceite fechados aqui:
- CSV com exatamente as colunas `nome;email;telefone;consentimento_em`,
  ordenado por nome
- `consentimento_em` só com a data (`AAAA-MM-DD`); o banco continua com hora
- Nome `=HYPERLINK(...)` sai como `'=HYPERLINK(...)`
- Visitantes de outra edição não entram no CSV
- Edição sem visitantes → CSV só com o cabeçalho
- Nenhum log contém dado pessoal: só usuário, data/hora e número de linhas
- Número fixo de consultas
"""

import csv
import io
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from cadastro.tests import fabricas as cadastro
from resultados.tests import cenario
from votacao.models import Visitante
from votacao.tests import fabricas as votacao

pytestmark = pytest.mark.django_db

BRASILIA = ZoneInfo("America/Sao_Paulo")
BOM = "﻿"
CABECALHO = "nome;email;telefone;consentimento_em\r\n"


@pytest.fixture
def admin(client):
    client.force_login(cenario.usuario(nome="coordenacao", perms=("exportar_visitantes",)))
    return client


def exportar(client, edicao):
    resposta = client.get(reverse("resultados:visitantes_csv", args=[edicao.pk]))
    assert resposta.status_code == 200
    return resposta, resposta.content.decode("utf-8")


def linhas(texto):
    assert texto.startswith(BOM)
    return list(csv.reader(io.StringIO(texto[len(BOM) :]), delimiter=";"))


def test_cabecalho_ordem_por_nome_bom_e_separador(admin):
    ed = cadastro.edicao()
    # Cadastro fora de ordem; acento e caixa não mudam a ordem alfabética.
    votacao.visitante(ed, nome="carla Souza", email="carla@example.com", telefone="17999990003")
    votacao.visitante(ed, nome="Bruno Lima", email="bruno@example.com")
    votacao.visitante(ed, nome="Ágata Reis", email="agata@example.com", telefone="1733330001")
    resposta, texto = exportar(admin, ed)
    assert resposta["Content-Type"] == "text/csv; charset=utf-8"
    assert resposta["Content-Disposition"] == f'attachment; filename="visitantes-edicao-{ed.pk}.csv"'
    assert "no-store" in resposta["Cache-Control"]
    assert texto.startswith(BOM + CABECALHO)
    assert linhas(texto) == [
        ["nome", "email", "telefone", "consentimento_em"],
        ["Ágata Reis", "agata@example.com", "1733330001", "2026-10-29"],
        ["Bruno Lima", "bruno@example.com", "", "2026-10-29"],
        ["carla Souza", "carla@example.com", "17999990003", "2026-10-29"],
    ]


def test_consentimento_so_com_a_data_local_e_banco_intacto(admin):
    ed = cadastro.edicao()
    # 22h em Brasília = 01h do dia 30 em UTC: a data é a do evento (29).
    aceite = datetime(2026, 10, 29, 22, 0, tzinfo=BRASILIA)
    visitante = votacao.visitante(ed, consentimento_em=aceite)
    _, texto = exportar(admin, ed)
    assert linhas(texto)[1][3] == "2026-10-29"
    assert not re.search(r"\d{2}:\d{2}", texto)
    visitante.refresh_from_db()
    assert visitante.consentimento_em == aceite


@pytest.mark.parametrize(
    "nome",
    ['=HYPERLINK("http://exemplo.invalid","clique")', "+5+5", "-2+3", "@SOMA(A1)", "\t=1", "\r=1"],
)
def test_inicio_de_formula_ganha_apostrofo(admin, nome):
    ed = cadastro.edicao()
    votacao.visitante(ed, nome=nome, email="=1+1@example.com")
    _, texto = exportar(admin, ed)
    assert linhas(texto)[1][:2] == ["'" + nome, "'=1+1@example.com"]


def test_valor_comum_sai_sem_apostrofo_e_separador_no_nome_fica_entre_aspas(admin):
    ed = cadastro.edicao()
    votacao.visitante(ed, nome="Ana; da Silva - Jr.", email="ana-silva@example.com")
    _, texto = exportar(admin, ed)
    assert '"Ana; da Silva - Jr.";ana-silva@example.com;;2026-10-29\r\n' in texto
    assert linhas(texto)[1][0] == "Ana; da Silva - Jr."


def test_so_visitantes_da_edicao_pedida(admin):
    evento, ensaio = cadastro.edicao(nome="2026/2"), cadastro.edicao(nome="Ensaio 2026/2")
    votacao.visitante(evento, nome="Do Evento", email="evento@example.com")
    votacao.visitante(ensaio, nome="Do Ensaio", email="ensaio@example.com")
    _, texto = exportar(admin, evento)
    assert [linha[0] for linha in linhas(texto)[1:]] == ["Do Evento"]
    assert "ensaio@example.com" not in texto


def test_edicao_sem_visitantes_so_cabecalho(admin):
    votacao.visitante(cadastro.edicao(nome="Outra"))
    _, texto = exportar(admin, cadastro.edicao(nome="Vazia"))
    assert texto == BOM + CABECALHO


def test_log_do_export_sem_dado_pessoal(admin, caplog):
    ed = cadastro.edicao()
    votacao.visitante(ed, nome="Fulana Fictícia", email="fulana@example.com", telefone="17988887777")
    votacao.visitante(ed, nome="Beltrano Fictício", email="beltrano@example.com")
    with caplog.at_level(logging.DEBUG):
        exportar(admin, ed)
    registros = [r for r in caplog.records if r.name == "resultados.views"]
    assert len(registros) == 1 and registros[0].levelno == logging.INFO
    assert re.fullmatch(
        r"export de visitantes por coordenacao em \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}, 2 linhas",
        registros[0].getMessage(),
    )
    tudo = caplog.text + "".join(r.getMessage() for r in caplog.records)
    for dado in ("Fulana", "Beltrano", "fulana@example.com", "beltrano@example.com", "17988887777"):
        assert dado not in tudo


def test_log_do_export_passa_do_nivel_do_root():
    """O root do LOGGING é WARNING; a linha INFO do export não pode sumir."""
    assert logging.getLogger("resultados.views").isEnabledFor(logging.INFO)


def test_export_negado_nao_registra(client, caplog):
    client.force_login(cenario.usuario(perms=("ver_resultados",)))
    ed = cadastro.edicao()
    with caplog.at_level(logging.INFO, logger="resultados.views"):
        assert client.get(reverse("resultados:visitantes_csv", args=[ed.pk])).status_code == 403
    assert not [r for r in caplog.records if r.name == "resultados.views"]


def test_export_nao_altera_visitantes(admin):
    ed = cadastro.edicao()
    votacao.visitante(ed, nome="=Fórmula", email="formula@example.com")
    antes = list(Visitante.objects.values())
    exportar(admin, ed)
    assert list(Visitante.objects.values()) == antes


def _consultas(client, edicao):
    with CaptureQueriesContext(connection) as capturadas:
        exportar(client, edicao)
    return len(capturadas)


def test_numero_de_consultas_nao_depende_do_tamanho(admin):
    pequena, grande = cadastro.edicao(nome="Pequena"), cadastro.edicao(nome="Grande")
    votacao.visitante(pequena)
    for i in range(40):
        votacao.visitante(grande, nome=f"Visitante {i}", email=f"v{i}@example.com")
    assert _consultas(admin, grande) == _consultas(admin, pequena)
