"""Critérios de aceite "Modelo" e "Moderação" (specs/01-cadastro.md)."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from cadastro.models import Curso, Edicao, Integrante, Projeto, Turma
from cadastro.tests import fabricas

pytestmark = pytest.mark.django_db


def test_so_uma_edicao_ativa():
    fabricas.edicao(nome="2026/2", ativa=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        fabricas.edicao(nome="Ensaio 2026/2", ativa=True)


def test_varias_edicoes_inativas_sao_permitidas():
    fabricas.edicao(nome="2026/1")
    fabricas.edicao(nome="2026/2")
    assert Edicao.objects.ativa() is None


def test_edicao_ativa_e_encontrada():
    fabricas.edicao(nome="2026/1")
    atual = fabricas.edicao(nome="2026/2", ativa=True)
    assert Edicao.objects.ativa() == atual


@pytest.mark.parametrize("banca,publico", [("0.70", "0.20"), ("0.80", "0.30"), ("1.10", "-0.10")])
def test_pesos_que_nao_somam_um_sao_recusados_pelo_banco(banca, publico):
    with pytest.raises(IntegrityError), transaction.atomic():
        fabricas.edicao(peso_banca=Decimal(banca), peso_publico=Decimal(publico))


def test_pesos_padrao_sao_70_30():
    e = fabricas.edicao()
    assert (e.peso_banca, e.peso_publico) == (Decimal("0.70"), Decimal("0.30"))


def test_turma_repetida_na_mesma_edicao_e_recusada():
    t = fabricas.turma()
    with pytest.raises(IntegrityError), transaction.atomic():
        Turma.objects.create(edicao=t.edicao, curso=t.curso, numero_periodo=3, tipo_periodo="semestre")


def test_mesma_turma_em_outra_edicao_e_permitida():
    t = fabricas.turma()
    outra = fabricas.edicao(nome="Ensaio 2026/2")
    Turma.objects.create(edicao=outra, curso=t.curso, numero_periodo=3, tipo_periodo="semestre")


def test_periodo_fora_de_1_a_12_e_recusado_pelo_banco():
    t = fabricas.turma()
    with pytest.raises(IntegrityError), transaction.atomic():
        Turma.objects.create(edicao=t.edicao, curso=t.curso, numero_periodo=13, tipo_periodo="ano")


def test_apagar_turma_ou_curso_com_projeto_e_bloqueado():
    p = fabricas.projeto()
    with pytest.raises(ProtectedError):
        p.turma.delete()
    with pytest.raises(ProtectedError):
        p.turma.curso.delete()


def test_rotulo_da_turma():
    e = fabricas.edicao()
    dsm = fabricas.turma(e, fabricas.curso("DSM"))
    adm = fabricas.turma(e, fabricas.curso("ADM", Curso.Unidade.ETEC), numero_periodo=2, tipo_periodo="ano", turno="tarde")
    assert dsm.rotulo == "DSM — 3º semestre"
    assert adm.rotulo == "ADM — 2º ano (tarde)"


def test_slug_gerado_unico_e_imutavel():
    t = fabricas.turma()
    a = fabricas.projeto(t, titulo="Agenda Escolar Inteligente")
    b = fabricas.projeto(t, titulo="Agenda Escolar Inteligente")
    assert a.slug == "agenda-escolar-inteligente"
    assert b.slug == "agenda-escolar-inteligente-2"

    a.titulo = "Outro nome"
    a.save()
    a.refresh_from_db()
    assert a.slug == "agenda-escolar-inteligente"


def test_slug_de_titulo_sem_letras():
    assert fabricas.projeto(titulo="!!!").slug == "projeto"


def test_integrante_etec_so_primeiro_nome():
    etec = fabricas.turma(curso_=fabricas.curso("ADM", Curso.Unidade.ETEC), numero_periodo=2, tipo_periodo="ano")
    p = fabricas.projeto(etec)
    with pytest.raises(ValidationError):
        Integrante(projeto=p, nome="Ana Souza").full_clean()
    Integrante(projeto=p, nome="Ana").full_clean()


def test_integrante_fatec_aceita_nome_completo():
    Integrante(projeto=fabricas.projeto(), nome="Ana Souza").full_clean()


def test_link_so_https():
    p = fabricas.projeto()
    p.link_repositorio = "http://github.com/x/y"
    with pytest.raises(ValidationError):
        p.full_clean()


# --- Moderação ------------------------------------------------------------------


def _completo(**campos):
    p = fabricas.projeto(resumo="Resumo", descricao="Descrição", capa=fabricas.imagem(), status="em_revisao", **campos)
    Integrante.objects.create(projeto=p, nome="Ana")
    return p


def test_publicar_projeto_completo(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    p = _completo()
    assert p.publicar() == []
    p.refresh_from_db()
    assert p.status == Projeto.Status.PUBLICADO
    assert p.publicado_em is not None


def test_publicar_sem_capa_fica_em_revisao():
    p = fabricas.projeto(resumo="R", descricao="D", status="em_revisao")
    Integrante.objects.create(projeto=p, nome="Ana")
    assert p.publicar() == ["capa"]
    p.refresh_from_db()
    assert p.status == Projeto.Status.EM_REVISAO


def test_pendencias_listam_tudo_que_falta():
    assert fabricas.projeto().pendencias_para_publicar() == ["capa", "resumo", "descrição", "integrantes"]


def test_republicar_nao_muda_publicado_em(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    p = _completo()
    p.publicar()
    primeira = p.publicado_em
    p.motivo_ajustes = "Trocar a capa"
    p.devolver_para_ajustes()
    p.publicar()
    p.refresh_from_db()
    assert p.publicado_em == primeira


def test_devolver_exige_motivo():
    p = fabricas.projeto(status="em_revisao")
    assert p.devolver_para_ajustes() is False
    p.refresh_from_db()
    assert p.status == Projeto.Status.EM_REVISAO

    p.motivo_ajustes = "Descrição muito curta"
    assert p.devolver_para_ajustes() is True
    p.refresh_from_db()
    assert p.status == Projeto.Status.AJUSTES
