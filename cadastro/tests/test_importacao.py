"""Critérios de aceite "Importação" (specs/01-cadastro.md)."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from cadastro.models import Curso, Projeto, Turma
from cadastro.seguranca import hash_ra
from cadastro.tests import fabricas

pytestmark = pytest.mark.django_db

CABECALHO = ["Curso", "Turma", "Período da turma", "Nome do projeto", "Nome do representante", "RA do representante"]
RA_A = "1234567890123"
RA_B = "9876543210987"


@pytest.fixture
def edicao():
    e = fabricas.edicao()
    dsm = fabricas.curso("DSM")
    gtur = fabricas.curso("GTUR")
    fabricas.turma(e, dsm, numero_periodo=3)
    fabricas.turma(e, gtur, numero_periodo=2)
    return e


def _csv(tmp_path, linhas, separador=";", bom=False, cabecalho=CABECALHO, nome="lista.csv", codificacao="utf-8"):
    texto = "\n".join(separador.join(celulas) for celulas in [cabecalho, *linhas]) + "\n"
    if bom:
        texto = "﻿" + texto
    caminho = tmp_path / nome
    caminho.write_bytes(texto.encode(codificacao))
    return caminho


def _linha(titulo="Agenda Escolar", ra=RA_A, curso="DSM — Desenvolvimento de Software Multiplataforma",
           turma="3º semestre", periodo="Semestre", representante="Maria Teste"):
    return [curso, turma, periodo, titulo, representante, ra]


def _rodar(edicao, caminho, aplicar=False):
    saida, erros = StringIO(), StringIO()
    args = [str(edicao.pk), str(caminho)] + (["--aplicar"] if aplicar else [])
    try:
        call_command("importar_lista", *args, stdout=saida, stderr=erros)
        falhou = None
    except CommandError as erro:
        falhou = str(erro)
    return saida.getvalue() + erros.getvalue() + (falhou or ""), falhou


# --- Formato -------------------------------------------------------------------


@pytest.mark.parametrize("separador,bom", [(";", False), (";", True), (",", False), (",", True)])
def test_separador_e_bom_dao_o_mesmo_resultado(edicao, tmp_path, separador, bom):
    linhas = [_linha("Agenda Escolar", RA_A), _linha("Guia de Turismo", RA_B, "GTUR — Gestão de Turismo", "2º semestre")]
    _, falhou = _rodar(edicao, _csv(tmp_path, linhas, separador, bom), aplicar=True)
    assert falhou is None
    assert sorted(Projeto.objects.values_list("titulo", flat=True)) == ["Agenda Escolar", "Guia de Turismo"]


def test_sem_aplicar_nada_e_gravado(edicao, tmp_path):
    saida, falhou = _rodar(edicao, _csv(tmp_path, [_linha()]))
    assert falhou is None
    assert "linha 2: criado — Agenda Escolar" in saida
    assert "Simulação" in saida
    assert not Projeto.objects.exists()


def test_projeto_criado_com_hmac_do_ra_e_pre_cadastrado(edicao, tmp_path):
    _rodar(edicao, _csv(tmp_path, [_linha()]), aplicar=True)
    p = Projeto.objects.get()
    assert p.ra_hmac == hash_ra(RA_A)
    assert p.status == Projeto.Status.PRE_CADASTRADO
    assert p.turma.rotulo == "DSM — 3º semestre"


def test_uma_linha_com_erro_nada_e_gravado_mesmo_com_aplicar(edicao, tmp_path):
    linhas = [_linha("Agenda Escolar", RA_A), _linha("Outro", RA_B, curso="XYZ — Inexistente")]
    saida, falhou = _rodar(edicao, _csv(tmp_path, linhas), aplicar=True)
    assert falhou is not None
    assert "linha 3: erro — Outro (curso inexistente)" in saida
    assert not Projeto.objects.exists()


def test_linha_de_exemplo_e_vazia_sao_ignoradas(edicao, tmp_path):
    linhas = [_linha("EXEMPLO — Agenda Escolar Inteligente", "1234567890123"), ["", "", "", "", "", ""], _linha("Real", RA_B)]
    saida, falhou = _rodar(edicao, _csv(tmp_path, linhas), aplicar=True)
    assert falhou is None
    assert list(Projeto.objects.values_list("titulo", flat=True)) == ["Real"]
    assert "linha de exemplo" in saida


# --- Idempotência ----------------------------------------------------------------


def test_rodar_duas_vezes_nao_duplica(edicao, tmp_path):
    caminho = _csv(tmp_path, [_linha()])
    _rodar(edicao, caminho, aplicar=True)
    saida, _ = _rodar(edicao, caminho, aplicar=True)
    assert Projeto.objects.count() == 1
    assert "ignorado — Agenda Escolar (sem alterações)" in saida


@pytest.mark.parametrize("variacao", ["  agenda   escolar ", "AGENDA ESCOLAR", "Agênda Escolar"])
def test_titulo_com_variacao_e_o_mesmo_projeto(edicao, tmp_path, variacao):
    _rodar(edicao, _csv(tmp_path, [_linha("Agenda Escolar")], nome="a.csv"), aplicar=True)
    _rodar(edicao, _csv(tmp_path, [_linha(variacao, representante="Outra Pessoa")], nome="b.csv"), aplicar=True)
    p = Projeto.objects.get()
    assert p.titulo == "Agenda Escolar"
    assert p.representante_nome == "Outra Pessoa"


def test_projeto_ja_reivindicado_e_ignorado_e_ra_nao_muda(edicao, tmp_path):
    _rodar(edicao, _csv(tmp_path, [_linha()], nome="a.csv"), aplicar=True)
    Projeto.objects.update(reivindicado_em=timezone.now())
    saida, _ = _rodar(edicao, _csv(tmp_path, [_linha(ra=RA_B)], nome="b.csv"), aplicar=True)
    assert "já reivindicado" in saida
    assert Projeto.objects.get().ra_hmac == hash_ra(RA_A)


# --- Turma e turno ----------------------------------------------------------------


def test_turma_inexistente_e_erro(edicao, tmp_path):
    saida, falhou = _rodar(edicao, _csv(tmp_path, [_linha(turma="5º semestre")]))
    assert falhou and "turma inexistente" in saida


def test_turma_ambigua_sem_turno_e_com_turno(edicao, tmp_path):
    dsm = Curso.objects.get(sigla="DSM")
    Turma.objects.filter(curso=dsm).update(turno="noite")
    fabricas.turma(edicao, dsm, numero_periodo=3, turno="manha")

    saida, falhou = _rodar(edicao, _csv(tmp_path, [_linha()], nome="sem.csv"), aplicar=True)
    assert falhou and "turma ambígua — informe o turno" in saida
    assert not Projeto.objects.exists()

    com_turno = _csv(tmp_path, [_linha() + ["manhã"]], cabecalho=CABECALHO + ["Turno"], nome="com.csv")
    _, falhou = _rodar(edicao, com_turno, aplicar=True)
    assert falhou is None
    assert Projeto.objects.get().turma.turno == "manha"


def test_periodo_divergente_e_erro(edicao, tmp_path):
    saida, falhou = _rodar(edicao, _csv(tmp_path, [_linha(turma="2º ano", periodo="Semestre")]))
    assert falhou and "diferente de" in saida


# --- RA ------------------------------------------------------------------------


def test_ra_de_outro_projeto_da_edicao_em_importacao_anterior_e_erro(edicao, tmp_path):
    _rodar(edicao, _csv(tmp_path, [_linha("Agenda Escolar", RA_A)], nome="a.csv"), aplicar=True)
    saida, falhou = _rodar(edicao, _csv(tmp_path, [_linha("Outro Projeto", RA_A)], nome="b.csv"), aplicar=True)
    assert falhou and "RA de outro projeto da edição" in saida
    assert Projeto.objects.count() == 1


def test_mesmo_ra_em_outra_edicao_e_aceito(edicao, tmp_path):
    _rodar(edicao, _csv(tmp_path, [_linha(ra=RA_A)], nome="a.csv"), aplicar=True)
    ensaio = fabricas.edicao(nome="Ensaio 2026/2")
    fabricas.turma(ensaio, Curso.objects.get(sigla="DSM"), numero_periodo=3)
    _, falhou = _rodar(ensaio, _csv(tmp_path, [_linha(ra=RA_A)], nome="b.csv"), aplicar=True)
    assert falhou is None
    assert Projeto.objects.count() == 2


def test_ra_repetido_no_arquivo_e_erro(edicao, tmp_path):
    saida, falhou = _rodar(edicao, _csv(tmp_path, [_linha("A", RA_A), _linha("B", RA_A)]))
    assert falhou and "linha 3: erro" in saida and "RA de outro projeto" in saida


@pytest.mark.parametrize("ra", ["", "12a45678", "1234"])
def test_ra_invalido_e_erro(edicao, tmp_path, ra):
    saida, falhou = _rodar(edicao, _csv(tmp_path, [_linha(ra=ra)]))
    assert falhou and "RA inválido" in saida


def test_ra_nunca_aparece_na_saida(edicao, tmp_path):
    linhas = [_linha("A", RA_A), _linha("B", RA_A), _linha("C", "12a45678901"), _linha("D", RA_B, curso="XYZ")]
    saida, _ = _rodar(edicao, _csv(tmp_path, linhas))
    for ra in [RA_A, RA_B, "12a45678901", hash_ra(RA_A)]:
        assert ra not in saida


# --- Limites e erros de arquivo -------------------------------------------------------


def test_representante_com_121_caracteres_e_erro(edicao, tmp_path):
    saida, falhou = _rodar(edicao, _csv(tmp_path, [_linha(representante="x" * 121)]))
    assert falhou and "representante" in saida


def test_projeto_repetido_no_arquivo_e_erro(edicao, tmp_path):
    saida, falhou = _rodar(edicao, _csv(tmp_path, [_linha("Agenda", RA_A), _linha("agenda", RA_B)]))
    assert falhou and "projeto repetido no arquivo (linha 2)" in saida


def test_edicao_inexistente(tmp_path):
    with pytest.raises(CommandError, match="não existe"):
        call_command("importar_lista", "999", str(tmp_path / "x.csv"), stdout=StringIO())


def test_arquivo_ausente(edicao, tmp_path):
    with pytest.raises(CommandError, match="Não foi possível ler"):
        call_command("importar_lista", str(edicao.pk), str(tmp_path / "nao-existe.csv"), stdout=StringIO())


def test_arquivo_que_nao_e_utf8(edicao, tmp_path):
    caminho = _csv(tmp_path, [_linha("Gestão")], codificacao="cp1252")
    _, falhou = _rodar(edicao, caminho, aplicar=True)
    assert falhou and "UTF-8" in falhou
    assert not Projeto.objects.exists()


def test_cabecalho_sem_coluna_obrigatoria(edicao, tmp_path):
    _, falhou = _rodar(edicao, _csv(tmp_path, [_linha()[:5]], cabecalho=CABECALHO[:5]))
    assert falhou and "RA do representante" in falhou


def test_cabecalho_com_coluna_repetida(edicao, tmp_path):
    _, falhou = _rodar(edicao, _csv(tmp_path, [_linha() + ["x"]], cabecalho=CABECALHO + ["Turma"]))
    assert falhou and "repetida" in falhou
