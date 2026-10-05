"""Critérios de aceite "Modelo" e "Moderação" (specs/01-cadastro.md)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

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


@pytest.mark.parametrize("banca,publico", [("0.70", "0.20"), ("0.80", "0.30")])
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
    p.status = Projeto.Status.EM_REVISAO  # o grupo salvou de novo (spec 02)
    p.save()
    p.publicar()
    p.refresh_from_db()
    assert p.status == Projeto.Status.PUBLICADO
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


# --- Travas (revisão do Renan no PR #16) ----------------------------------------


@pytest.mark.parametrize("banca,publico", [("1.70", "-0.70"), ("1.10", "-0.10")])
def test_pesos_fora_de_0_a_1_com_soma_1_sao_recusados(banca, publico):
    with pytest.raises(IntegrityError), transaction.atomic():
        fabricas.edicao(peso_banca=Decimal(banca), peso_publico=Decimal(publico))


@pytest.mark.parametrize("banca,publico", [("0.50", "0.50"), ("0.30", "0.70")])
def test_banca_precisa_pesar_mais_que_o_publico(banca, publico):
    e = fabricas.edicao(peso_banca=Decimal(banca), peso_publico=Decimal(publico))
    with pytest.raises(ValidationError) as erro:
        e.full_clean()
    assert "peso_banca" in erro.value.message_dict


def _abrir_votacao(e):
    Edicao.objects.filter(pk=e.pk).update(votacao_aberta_em=timezone.now())
    e.refresh_from_db()
    return e


def test_pesos_editaveis_antes_de_abrir_a_votacao():
    e = fabricas.edicao()
    e.peso_banca, e.peso_publico = Decimal("0.80"), Decimal("0.20")
    e.save()
    e.refresh_from_db()
    assert e.peso_banca == Decimal("0.80")


@pytest.mark.parametrize("encerrar", [False, True])
def test_pesos_travados_depois_de_abrir_ou_encerrar(encerrar):
    e = _abrir_votacao(fabricas.edicao())
    if encerrar:
        Edicao.objects.filter(pk=e.pk).update(votacao_encerrada_em=timezone.now())
        e.refresh_from_db()
    e.peso_banca, e.peso_publico = Decimal("0.80"), Decimal("0.20")
    with pytest.raises(ValidationError):
        e.save()
    e.refresh_from_db()
    assert (e.peso_banca, e.peso_publico) == (Decimal("0.70"), Decimal("0.30"))


def test_abertura_da_votacao_nao_muda_nem_e_apagada():
    e = _abrir_votacao(fabricas.edicao())
    original = e.votacao_aberta_em
    e.votacao_aberta_em = None
    with pytest.raises(ValidationError):
        e.save()
    e.refresh_from_db()
    assert e.votacao_aberta_em == original
    e.votacao_aberta_em = original - timedelta(hours=1)
    with pytest.raises(ValidationError):
        e.save()
    e.refresh_from_db()
    assert e.votacao_aberta_em == original


def test_encerramento_da_votacao_nao_muda_nem_e_apagado():
    e = _abrir_votacao(fabricas.edicao())
    Edicao.objects.filter(pk=e.pk).update(votacao_encerrada_em=timezone.now())
    e.refresh_from_db()
    original = e.votacao_encerrada_em
    for valor in (None, original + timedelta(hours=1)):
        e.votacao_encerrada_em = valor
        with pytest.raises(ValidationError):
            e.save()
        e.refresh_from_db()
        assert e.votacao_encerrada_em == original


def test_encerrar_pela_primeira_vez_e_permitido():
    e = _abrir_votacao(fabricas.edicao())
    e.votacao_encerrada_em = timezone.now()
    e.save(update_fields=["votacao_encerrada_em"])
    e.refresh_from_db()
    assert e.votacao_encerrada_em is not None


def test_outros_campos_da_edicao_continuam_editaveis_apos_abrir():
    e = _abrir_votacao(fabricas.edicao())
    e.banca_conferida_em = timezone.now()
    e.save(update_fields=["banca_conferida_em"])
    e.refresh_from_db()
    assert e.banca_conferida_em is not None


def test_edicao_nova_nasce_sem_conferencia_da_banca():
    e = fabricas.edicao(banca_conferida_em=timezone.now())
    e.refresh_from_db()
    assert e.banca_conferida_em is None


def _conferir(edicao_id, valor):
    """Como a conferência da spec 06: instância nova, update_fields."""
    e = Edicao.objects.get(pk=edicao_id)
    e.banca_conferida_em = valor
    e.save(update_fields=["banca_conferida_em"])


def test_save_completo_de_instancia_velha_nao_apaga_conferencia_nova():
    velha = _abrir_votacao(fabricas.edicao())
    conferida = timezone.now()
    _conferir(velha.pk, conferida)
    velha.ativa = True
    velha.save()  # ex.: form.save() do admin do cadastro, com a instância de antes
    velha.refresh_from_db()
    assert velha.banca_conferida_em == conferida and velha.ativa


def test_save_completo_de_instancia_velha_nao_regrava_conferencia_desfeita():
    e = _abrir_votacao(fabricas.edicao())
    _conferir(e.pk, timezone.now())
    velha = Edicao.objects.get(pk=e.pk)
    assert velha.banca_conferida_em is not None
    _conferir(e.pk, None)  # correção de nota desfaz (spec 06)
    velha.nome = "Outro nome"
    velha.save()
    velha.refresh_from_db()
    assert velha.banca_conferida_em is None and velha.nome == "Outro nome"


def test_update_fields_sem_o_campo_nao_o_escreve():
    e = _abrir_votacao(fabricas.edicao())
    e.banca_conferida_em = timezone.now()
    e.save(update_fields=["nome"])
    e.refresh_from_db()
    assert e.banca_conferida_em is None


def test_encerramento_exige_abertura_anterior():
    e = fabricas.edicao()
    with pytest.raises(IntegrityError), transaction.atomic():
        Edicao.objects.filter(pk=e.pk).update(votacao_encerrada_em=timezone.now())
    agora = timezone.now()
    with pytest.raises(IntegrityError), transaction.atomic():
        Edicao.objects.filter(pk=e.pk).update(votacao_aberta_em=agora, votacao_encerrada_em=agora - timedelta(minutes=1))


def test_turma_com_projeto_nao_muda_de_edicao_nem_de_curso():
    p = fabricas.projeto()
    t = p.turma
    edicao_original, curso_original = t.edicao_id, t.curso_id
    t.edicao = fabricas.edicao(nome="Ensaio 2026/2")
    with pytest.raises(ValidationError):
        t.save()
    t.refresh_from_db()
    assert t.edicao_id == edicao_original
    t.curso = fabricas.curso("GTUR")
    with pytest.raises(ValidationError):
        t.save()
    t.refresh_from_db()
    assert t.curso_id == curso_original


def test_turma_sem_projeto_pode_mudar():
    t = fabricas.turma()
    t.curso = fabricas.curso("GTUR")
    t.save()


def test_projeto_nao_muda_para_turma_de_outra_edicao():
    p = fabricas.projeto()
    ensaio = fabricas.turma(fabricas.edicao(nome="Ensaio 2026/2"), p.turma.curso)
    original = p.turma_id
    p.turma = ensaio
    with pytest.raises(ValidationError):
        p.save()
    p.refresh_from_db()
    assert p.turma_id == original


def test_projeto_muda_de_turma_na_mesma_edicao_antes_de_abrir():
    p = fabricas.projeto()
    outra = fabricas.turma(p.turma.edicao, p.turma.curso, numero_periodo=2)
    p.turma = outra
    p.save()


def test_com_votacao_aberta_status_e_turma_nao_mudam(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    p = _completo()
    p.publicar()
    _abrir_votacao(p.turma.edicao)
    p.refresh_from_db()

    p.motivo_ajustes = "Trocar a capa"
    with pytest.raises(ValidationError):
        p.devolver_para_ajustes()

    p.refresh_from_db()
    assert p.status == Projeto.Status.PUBLICADO

    turma_original = p.turma_id
    p.turma = fabricas.turma(p.turma.edicao, p.turma.curso, numero_periodo=2)
    with pytest.raises(ValidationError):
        p.save()

    p.refresh_from_db()
    assert p.status == Projeto.Status.PUBLICADO
    assert p.turma_id == turma_original


def test_com_votacao_aberta_publicar_e_recusado(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    p = _completo()
    _abrir_votacao(p.turma.edicao)
    p.refresh_from_db()
    with pytest.raises(ValidationError):
        p.publicar()
    p.refresh_from_db()
    assert p.status == Projeto.Status.EM_REVISAO


def test_com_votacao_aberta_conteudo_do_projeto_ainda_e_editavel():
    p = fabricas.projeto()
    _abrir_votacao(p.turma.edicao)
    p.refresh_from_db()
    p.resumo = "Correção de digitação"
    p.save()


def test_status_nao_aparece_no_formulario():
    from django.forms import modelform_factory

    campos = modelform_factory(Projeto, exclude=[]).base_fields
    for nome in ["status", "slug", "ra_hmac", "token_edicao_hash"]:
        assert nome not in campos


# --- Estado de origem das ações e prazo (parecer do Renan no PR #16) -----------


@pytest.mark.parametrize("origem", ["pre_cadastrado", "ajustes"])
def test_publicar_so_a_partir_de_em_revisao(settings, tmp_path, origem):
    settings.MEDIA_ROOT = tmp_path
    p = _completo()
    Projeto.objects.filter(pk=p.pk).update(status=origem)
    p.refresh_from_db()
    assert p.publicar() != []
    p.refresh_from_db()
    assert p.status == origem


@pytest.mark.parametrize("origem", ["pre_cadastrado", "ajustes"])
def test_devolver_so_a_partir_de_em_revisao_ou_publicado(origem):
    p = fabricas.projeto(status=origem, motivo_ajustes="Motivo")
    assert p.devolver_para_ajustes() is False
    p.refresh_from_db()
    assert p.status == origem


def test_devolver_projeto_publicado(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    p = _completo()
    p.publicar()
    p.motivo_ajustes = "Retire as fotos em que aparecem pessoas"
    assert p.devolver_para_ajustes() is True


@pytest.mark.parametrize("campo", ["resumo", "descricao"])
def test_pendencia_de_cada_campo_de_texto(settings, tmp_path, campo):
    settings.MEDIA_ROOT = tmp_path
    p = _completo()
    setattr(p, campo, "   ")
    assert p.pendencias_para_publicar() == [{"resumo": "resumo", "descricao": "descrição"}[campo]]


def test_pendencia_sem_integrante(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    p = _completo()
    p.integrantes.all().delete()
    assert p.pendencias_para_publicar() == ["integrantes"]


def test_pre_cadastro_nasce_so_com_turma_titulo_e_representante():
    p = fabricas.projeto()
    p.full_clean()
    assert p.status == Projeto.Status.PRE_CADASTRADO


def test_prazo_de_edicao_antes_no_limite_e_depois():
    agora = timezone.now()
    e = fabricas.edicao(prazo_edicao=agora + timedelta(minutes=1))
    assert e.edicao_aberta() is True
    e.prazo_edicao = agora - timedelta(minutes=1)
    assert e.edicao_aberta() is False


def test_prazo_de_edicao_exatamente_no_limite(monkeypatch):
    agora = timezone.now()
    e = fabricas.edicao(prazo_edicao=agora)
    monkeypatch.setattr(timezone, "now", lambda: agora)
    assert e.edicao_aberta() is True


def test_edicao_nasce_sem_banca_conferida():
    assert fabricas.edicao().banca_conferida_em is None


# --- Parecer do #17 --------------------------------------------------------------


def test_pesos_atribuidos_como_texto_nao_disparam_a_trava():
    e = _abrir_votacao(fabricas.edicao())
    e.peso_banca, e.peso_publico = "0.70", "0.3"
    e.save()


def test_ra_unico_por_edicao():
    from cadastro.seguranca import hash_ra

    t = fabricas.turma()
    fabricas.projeto(t, titulo="A", ra_hmac=hash_ra("1234567"))
    outro = fabricas.projeto(t, titulo="B", ra_hmac=hash_ra("7654321"))
    outro.ra_hmac = hash_ra("1234567")
    with pytest.raises(ValidationError) as erro:
        outro.full_clean()
    assert "1234567" not in str(erro.value)


def test_mesmo_ra_em_outra_edicao_e_aceito():
    from cadastro.seguranca import hash_ra

    fabricas.projeto(titulo="A", ra_hmac=hash_ra("1234567"))
    ensaio = fabricas.turma(fabricas.edicao(nome="Ensaio 2026/2"), fabricas.curso("GTUR"))
    fabricas.projeto(ensaio, titulo="A", ra_hmac=hash_ra("1234567")).full_clean()


def test_trava_restaura_o_status_em_memoria(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    p = _completo()
    _abrir_votacao(p.turma.edicao)
    with pytest.raises(ValidationError):
        p.publicar()
    assert p.status == Projeto.Status.EM_REVISAO
    assert p.publicado_em is None


@pytest.mark.django_db(transaction=True)
def test_publicar_espera_a_abertura_concorrente_da_votacao(settings, tmp_path):
    """Abrir a votação e publicar ao mesmo tempo: a trava vence (linha da edição travada)."""
    import threading
    import time

    from django.db import connection

    settings.MEDIA_ROOT = tmp_path
    p = _completo()
    e = p.turma.edicao
    travou = threading.Event()

    def abrir_votacao():
        try:
            with transaction.atomic():
                Edicao.objects.select_for_update().get(pk=e.pk)
                Edicao.objects.filter(pk=e.pk).update(votacao_aberta_em=timezone.now())
                travou.set()
                time.sleep(0.5)  # publicar() tenta agora e precisa esperar
        finally:
            connection.close()

    t = threading.Thread(target=abrir_votacao)
    t.start()
    travou.wait(5)
    with pytest.raises(ValidationError):
        p.publicar()
    t.join()
    p.refresh_from_db()
    assert p.status == Projeto.Status.EM_REVISAO


# --- Ajustes do Renan no #17 -------------------------------------------------------


def test_slug_nao_muda_nem_pelo_model():
    p = fabricas.projeto(titulo="Agenda Escolar")
    p.slug = "outro"
    with pytest.raises(ValidationError):
        p.save(update_fields=["slug"])
    p.refresh_from_db()
    assert p.slug == "agenda-escolar"


def test_votacao_foi_aberta_nulo_passado_instante_e_futuro(monkeypatch):
    agora = timezone.now()
    monkeypatch.setattr(timezone, "now", lambda: agora)
    e = fabricas.edicao()
    assert e.votacao_foi_aberta() is False  # nulo
    e.votacao_aberta_em = agora - timedelta(minutes=1)
    assert e.votacao_foi_aberta() is True  # passado
    e.votacao_aberta_em = agora
    assert e.votacao_foi_aberta() is True  # instante exato
    e.votacao_aberta_em = agora + timedelta(minutes=1)
    assert e.votacao_foi_aberta() is False  # futuro
