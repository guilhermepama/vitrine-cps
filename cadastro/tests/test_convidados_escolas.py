"""ADR-013 no cadastro (specs/01-cadastro.md): pesos de convidados e do boletim,
unidade "Ensino Médio", turma por escola e regras de menores."""

from decimal import Decimal
from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

from cadastro.models import Curso, Edicao, Integrante, Projeto, Turma
from cadastro.tests import fabricas

pytestmark = pytest.mark.django_db
D = Decimal


# --- Pesos ---------------------------------------------------------------------


def test_pesos_novos_tem_padrao_que_mantem_o_calculo_antigo():
    e = fabricas.edicao()
    assert (e.peso_banca, e.peso_convidados, e.peso_publico, e.peso_boletim_banca) == (D("0.70"), D("0.00"), D("0.30"), D("1.00"))


def test_pesos_desta_edicao_50_20_30_e_boletim_70_sao_aceitos():
    e = fabricas.edicao(peso_banca=D("0.50"), peso_convidados=D("0.20"), peso_publico=D("0.30"), peso_boletim_banca=D("0.70"))
    e.full_clean()
    e.refresh_from_db()
    assert e.peso_convidados == D("0.20") and e.peso_boletim_banca == D("0.70")


@pytest.mark.parametrize(
    "campos",
    [
        {"peso_banca": D("0.50"), "peso_convidados": D("0.30"), "peso_publico": D("0.30")},  # soma 1,10
        {"peso_banca": D("0.80"), "peso_convidados": D("-0.10"), "peso_publico": D("0.30")},  # negativo
        {"peso_boletim_banca": D("1.01")},
        {"peso_boletim_banca": D("-0.01")},
    ],
)
def test_pesos_invalidos_sao_barrados_no_banco(campos):
    with pytest.raises(IntegrityError), transaction.atomic():
        fabricas.edicao(**campos)


@pytest.mark.parametrize("campo,valor", [("peso_convidados", D("0.10")), ("peso_boletim_banca", D("0.60"))])
def test_pesos_novos_travam_depois_de_aberta_a_votacao(campo, valor):
    e = fabricas.edicao(peso_banca=D("0.50"), peso_convidados=D("0.20"), peso_publico=D("0.30"), peso_boletim_banca=D("0.70"))
    Edicao.objects.filter(pk=e.pk).update(votacao_aberta_em=timezone.now())
    e.refresh_from_db()
    setattr(e, campo, valor)
    if campo == "peso_convidados":
        e.peso_banca = D("0.60")
    with pytest.raises(ValidationError):
        e.save()
    e.refresh_from_db()
    assert (e.peso_convidados, e.peso_boletim_banca) == (D("0.20"), D("0.70"))


# --- Ensino Médio, escola e menores ------------------------------------------------


def test_etec_e_ensino_medio_atendem_menores_e_fatec_nao():
    assert not fabricas.curso("DSM").atende_menores
    assert fabricas.curso("ADM", Curso.Unidade.ETEC).atende_menores
    assert fabricas.curso("EM", Curso.Unidade.MEDIO).atende_menores


def _turmas_das_escolas(e):
    em = fabricas.curso("EM", Curso.Unidade.MEDIO)
    wil = fabricas.turma(e, em, numero_periodo=3, tipo_periodo=Turma.TipoPeriodo.ANO, escola="E.E. Wilquem")
    rn = fabricas.turma(e, em, numero_periodo=3, tipo_periodo=Turma.TipoPeriodo.ANO, escola="E.E. Reis Neves")
    return em, wil, rn


def test_duas_escolas_no_mesmo_curso_e_ano_com_rotulo_da_escola():
    e = fabricas.edicao()
    _, wil, rn = _turmas_das_escolas(e)
    assert wil.rotulo == "EM — 3º ano · E.E. Wilquem"
    assert rn.rotulo == "EM — 3º ano · E.E. Reis Neves"


def test_mesma_escola_duas_vezes_e_barrada_no_banco():
    e = fabricas.edicao()
    em, _, _ = _turmas_das_escolas(e)
    with pytest.raises(IntegrityError), transaction.atomic():
        fabricas.turma(e, em, numero_periodo=3, tipo_periodo=Turma.TipoPeriodo.ANO, escola="E.E. Wilquem")


def test_turma_sem_escola_continua_com_o_rotulo_de_antes():
    t = fabricas.turma(fabricas.edicao(), fabricas.curso("DSM"))
    assert t.escola == "" and t.rotulo == "DSM — 3º semestre"


def test_ensino_medio_so_aceita_o_primeiro_nome():
    e = fabricas.edicao()
    _, wil, _ = _turmas_das_escolas(e)
    projeto = fabricas.projeto(wil)
    with pytest.raises(ValidationError) as erro:
        Integrante(projeto=projeto, nome="Ana Souza").full_clean()
    assert "Ensino Médio" in str(erro.value)
    Integrante(projeto=projeto, nome="Ana", ordem=0).full_clean()


# --- Importação com a coluna Escola ------------------------------------------------

CABECALHO = ["Curso", "Turma", "Período da turma", "Nome do projeto", "Nome do representante", "RA do representante"]


def _csv(tmp_path, linhas, cabecalho, nome):
    caminho = tmp_path / nome
    caminho.write_text("\n".join(";".join(c) for c in [cabecalho, *linhas]) + "\n", encoding="utf-8")
    return caminho


def _rodar(edicao, caminho):
    saida = StringIO()
    try:
        call_command("importar_lista", str(edicao.pk), str(caminho), "--aplicar", stdout=saida, stderr=saida)
        return saida.getvalue(), None
    except CommandError as erro:
        return saida.getvalue() + str(erro), str(erro)


def test_importacao_separa_as_escolas_pela_coluna_escola(tmp_path):
    e = fabricas.edicao()
    _, wil, rn = _turmas_das_escolas(e)
    linha = ["EM — 3º ano do Ensino Médio", "3º ano", "Ano", "Horta na Escola", "Ana", "1234567890123"]

    saida, falhou = _rodar(e, _csv(tmp_path, [linha], CABECALHO, "sem.csv"))
    assert falhou and "turma ambígua — informe o turno ou a escola" in saida
    assert not Projeto.objects.exists()

    _, falhou = _rodar(e, _csv(tmp_path, [linha + ["e.e. reis neves"]], CABECALHO + ["Escola"], "com.csv"))
    assert falhou is None
    assert Projeto.objects.get().turma == rn
