"""Admin do cadastro e moderação (spec 01, 3/3)."""

from datetime import timedelta

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.admin.sites import site
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from cadastro.admin import ProjetoAdmin, ProjetoForm
from cadastro.models import Curso, Edicao, Integrante, Projeto
from cadastro.seguranca import hash_ra, hash_token
from cadastro.tests import fabricas

pytestmark = pytest.mark.django_db

RA = "9876543210123"
LISTA = reverse("admin:cadastro_projeto_changelist")
NOVO = reverse("admin:cadastro_projeto_add")


def _editar(projeto):
    return reverse("admin:cadastro_projeto_change", args=[projeto.pk])


def _versao(projeto):
    """O que o formulário de edição traz escondido: a versão do projeto ao abrir."""
    return Projeto.objects.get(pk=projeto.pk).atualizado_em.isoformat()


def _edicao(projeto, **campos):
    return {**_novo_projeto(projeto.turma, ra=campos.pop("ra", "")), "versao": _versao(projeto), **campos}


def _formsets(integrantes=(), imagens=0):
    dados = {
        "integrantes-TOTAL_FORMS": str(len(integrantes)),
        "integrantes-INITIAL_FORMS": "0",
        "integrantes-MIN_NUM_FORMS": "0",
        "integrantes-MAX_NUM_FORMS": "1000",
        "imagens-TOTAL_FORMS": str(imagens),
        "imagens-INITIAL_FORMS": "0",
        "imagens-MIN_NUM_FORMS": "0",
        "imagens-MAX_NUM_FORMS": "1000",
    }
    for i, nome in enumerate(integrantes):
        dados[f"integrantes-{i}-nome"] = nome
        dados[f"integrantes-{i}-ordem"] = str(i)
    return dados


def _novo_projeto(turma, ra=RA, titulo="Horta Comunitária", integrantes=()):
    return {
        "turma": turma.pk,
        "titulo": titulo,
        "representante_nome": "João Teste",
        "ra_representante": ra,
        **_formsets(integrantes),
    }


def _acao(client, acao, *projetos):
    return client.post(
        LISTA, {"action": acao, "_selected_action": [p.pk for p in projetos]}, follow=True
    )


def _mensagens(resposta):
    return " ".join(str(m) for m in resposta.context["messages"])


def _token_da_pagina(resposta):
    return resposta.content.decode().split("/grupo/editar/")[1].split("/")[0]


def _completo(turma_=None, **campos):
    p = fabricas.projeto(
        turma_, resumo="Resumo", descricao="Descrição", capa=fabricas.imagem(), status="em_revisao", **campos
    )
    Integrante.objects.create(projeto=p, nome="Ana")
    return p


@pytest.fixture
def midia(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


# --- Acesso (G15) ---------------------------------------------------------------


@pytest.mark.parametrize("modelo", ["edicao", "curso", "turma", "projeto"])
def test_anonimo_vai_para_o_login(client, modelo):
    resposta = client.get(reverse(f"admin:cadastro_{modelo}_changelist"))
    assert resposta.status_code == 302
    assert reverse("admin:login") in resposta["Location"]


@pytest.mark.parametrize("modelo", ["edicao", "curso", "turma", "projeto"])
def test_staff_sem_superusuario_recebe_403(client, modelo):
    staff = User.objects.create_user("digitacao", password="x", is_staff=True)
    client.force_login(staff)
    assert client.get(reverse(f"admin:cadastro_{modelo}_changelist")).status_code == 403


def test_superusuario_ve_as_listas_com_filtros(admin_client):
    p = fabricas.projeto()
    assert admin_client.get(LISTA, {"status": "pre_cadastrado", "turma__edicao__id__exact": p.turma.edicao_id}).status_code == 200
    assert admin_client.get(reverse("admin:cadastro_turma_changelist"), {"curso__id__exact": p.turma.curso_id}).status_code == 200
    assert admin_client.get(LISTA, {"q": "Agenda"}).status_code == 200


# --- Formulário do projeto: RA e campos escondidos ---------------------------------


def test_formulario_nao_tem_ra_hmac_token_nem_status_editavel(admin_client):
    p = fabricas.projeto()
    p.regerar_link()
    p.refresh_from_db()
    resposta = admin_client.get(_editar(p))
    form = resposta.context["adminform"].form
    for campo in ("ra_hmac", "token_edicao_hash", "status", "slug", "publicado_em", "reivindicado_em"):
        assert campo not in form.fields
    html = resposta.content.decode()
    assert p.ra_hmac not in html
    assert p.token_edicao_hash not in html


def test_criar_projeto_com_ra_grava_so_o_hmac(admin_client):
    turma = fabricas.turma()
    resposta = admin_client.post(NOVO, _novo_projeto(turma), follow=True)
    assert resposta.status_code == 200
    p = Projeto.objects.get(titulo="Horta Comunitária")
    assert p.ra_hmac == hash_ra(RA)
    assert p.status == Projeto.Status.PRE_CADASTRADO
    reaberto = admin_client.get(_editar(p)).content.decode()
    assert RA not in reaberto
    assert 'name="ra_representante"' in reaberto


def test_criar_projeto_sem_ra_e_recusado(admin_client):
    turma = fabricas.turma()
    resposta = admin_client.post(NOVO, _novo_projeto(turma, ra=""))
    assert resposta.status_code == 200
    assert "Informe o RA do representante." in resposta.content.decode()
    assert not Projeto.objects.exists()


def test_ra_invalido_e_recusado_sem_reexibir(admin_client):
    turma = fabricas.turma()
    resposta = admin_client.post(NOVO, _novo_projeto(turma, ra="12AB3456"))
    html = resposta.content.decode()
    assert "RA inválido" in html
    assert "12AB3456" not in html
    assert not Projeto.objects.exists()


def test_ra_que_ja_representa_outro_projeto_da_edicao_e_recusado(admin_client):
    existente = fabricas.projeto(ra_hmac=hash_ra(RA))
    resposta = admin_client.post(NOVO, _novo_projeto(existente.turma))
    html = resposta.content.decode()
    assert "Este RA já representa outro projeto nesta edição." in html
    assert RA not in html
    assert Projeto.objects.count() == 1


def test_editar_com_ra_vazio_mantem_o_atual(admin_client):
    p = fabricas.projeto()
    antes = p.ra_hmac
    dados = _edicao(p, titulo="Agenda Escolar 2")
    resposta = admin_client.post(_editar(p), dados, follow=True)
    assert resposta.status_code == 200
    p.refresh_from_db()
    assert p.titulo == "Agenda Escolar 2"
    assert p.ra_hmac == antes


def test_editar_com_ra_novo_troca_o_hmac(admin_client):
    p = fabricas.projeto()
    admin_client.post(_editar(p), _edicao(p, ra="555.666.777"), follow=True)
    p.refresh_from_db()
    assert p.ra_hmac == hash_ra("555666777")


# --- Formsets ---------------------------------------------------------------------


def test_decimo_primeiro_integrante_e_recusado(admin_client):
    turma = fabricas.turma()
    nomes = [f"Pessoa {i}" for i in range(11)]
    resposta = admin_client.post(NOVO, _novo_projeto(turma, integrantes=nomes))
    assert resposta.status_code == 200
    assert not Projeto.objects.exists()
    dez = _novo_projeto(turma, integrantes=nomes[:10])
    admin_client.post(NOVO, dez, follow=True)
    assert Projeto.objects.get().integrantes.count() == 10


def test_setima_imagem_extra_e_recusada(admin_client, midia):
    p = fabricas.projeto()
    dados = {**_edicao(p), **_formsets(imagens=7)}
    for i in range(7):
        dados[f"imagens-{i}-arquivo"] = fabricas.imagem(nome=f"f{i}.png")
        dados[f"imagens-{i}-ordem"] = str(i)
    resposta = admin_client.post(_editar(p), dados)
    assert resposta.status_code == 200
    assert p.imagens.count() == 0


def test_integrante_etec_com_sobrenome_e_recusado_ja_na_criacao(admin_client):
    turma = fabricas.turma(curso_=fabricas.curso("ADM", Curso.Unidade.ETEC))
    resposta = admin_client.post(NOVO, _novo_projeto(turma, integrantes=["Ana Souza"]))
    assert "só o primeiro nome" in resposta.content.decode()
    assert not Projeto.objects.exists()


# --- Moderação em lote --------------------------------------------------------------


def test_publicar_em_lote_publica_o_completo_e_lista_o_incompleto(admin_client, midia):
    turma = fabricas.turma()
    completo = _completo(turma)
    sem_capa = fabricas.projeto(turma, titulo="Sem Capa", resumo="R", descricao="D", status="em_revisao", ra_hmac=hash_ra("11111"))
    Integrante.objects.create(projeto=sem_capa, nome="Bia")
    resposta = _acao(admin_client, "acao_publicar", completo, sem_capa)
    completo.refresh_from_db()
    sem_capa.refresh_from_db()
    assert completo.status == Projeto.Status.PUBLICADO
    assert completo.publicado_em is not None
    assert sem_capa.status == Projeto.Status.EM_REVISAO
    texto = _mensagens(resposta)
    assert "1 projeto(s) publicado(s)" in texto
    assert "Sem Capa (falta: capa)" in texto


def test_publicar_de_pre_cadastrado_ou_ajustes_nao_muda(admin_client):
    turma = fabricas.turma()
    pre = fabricas.projeto(turma, titulo="Pre")
    ajustes = fabricas.projeto(turma, titulo="Ajustes", status="ajustes", ra_hmac=hash_ra("22222"))
    resposta = _acao(admin_client, "acao_publicar", pre, ajustes)
    assert set(Projeto.objects.values_list("status", flat=True)) == {"pre_cadastrado", "ajustes"}
    assert "0 projeto(s) publicado(s)" in _mensagens(resposta)


def test_devolver_em_lote_exige_motivo_e_estado(admin_client):
    turma = fabricas.turma()
    com_motivo = fabricas.projeto(turma, titulo="Com", status="em_revisao", motivo_ajustes="Capa borrada")
    sem_motivo = fabricas.projeto(turma, titulo="Sem", status="publicado", ra_hmac=hash_ra("33333"))
    pre = fabricas.projeto(turma, titulo="Pre", motivo_ajustes="x", ra_hmac=hash_ra("44444"))
    resposta = _acao(admin_client, "acao_devolver", com_motivo, sem_motivo, pre)
    for p in (com_motivo, sem_motivo, pre):
        p.refresh_from_db()
    assert com_motivo.status == Projeto.Status.AJUSTES
    assert sem_motivo.status == Projeto.Status.PUBLICADO
    assert pre.status == Projeto.Status.PRE_CADASTRADO
    texto = _mensagens(resposta)
    assert "1 projeto(s) devolvido(s)" in texto
    assert "Sem (sem motivo dos ajustes)" in texto
    assert "Pre (status pré-cadastrado)" in texto


def test_com_a_votacao_aberta_as_acoes_nao_mudam_nada(admin_client, midia):
    edicao = fabricas.edicao()
    turma = fabricas.turma(edicao)
    p = _completo(turma, motivo_ajustes="x")
    edicao.votacao_aberta_em = timezone.now() - timedelta(minutes=1)
    edicao.save()
    for acao in ("acao_publicar", "acao_devolver"):
        resposta = _acao(admin_client, acao, p)
        assert "votação da edição já aberta" in _mensagens(resposta)
        p.refresh_from_db()
        assert p.status == Projeto.Status.EM_REVISAO


# --- Link de edição -------------------------------------------------------------------


def test_regerar_link_mostra_uma_vez_e_invalida_o_anterior(admin_client, settings):
    settings.URL_PUBLICA = "https://vitrine.exemplo"
    p = fabricas.projeto()
    antigo = p.regerar_link()
    resposta = _acao(admin_client, "acao_regerar_link", p)
    p.refresh_from_db()
    assert "https://vitrine.exemplo/grupo/editar/" in resposta.content.decode()
    novo = _token_da_pagina(resposta)
    assert p.token_edicao_hash == hash_token(novo)
    assert p.token_edicao_hash != hash_token(antigo)
    assert novo not in admin_client.get(LISTA).content.decode()  # não reaparece


def test_link_regerado_nao_vai_para_cookie_nem_cache(admin_client):
    """A mensagem do Django viaja num cookie assinado, não cifrado: o token não pode ir nela."""
    p = fabricas.projeto()
    resposta = _acao(admin_client, "acao_regerar_link", p)
    token = _token_da_pagina(resposta)
    assert resposta.redirect_chain == []
    assert token not in str(resposta.cookies)
    assert token not in str(admin_client.cookies)
    assert "no-store" in resposta["Cache-Control"]
    assert resposta["Referrer-Policy"] == "no-referrer"


def test_regerar_link_exige_um_projeto_so(admin_client):
    turma = fabricas.turma()
    a = fabricas.projeto(turma, titulo="A")
    b = fabricas.projeto(turma, titulo="B", ra_hmac=hash_ra("55555"))
    resposta = _acao(admin_client, "acao_regerar_link", a, b)
    assert "Selecione exatamente um projeto" in _mensagens(resposta)
    assert not Projeto.objects.filter(token_edicao_hash__isnull=False).exists()


def test_revogar_link_apaga_o_hash(admin_client):
    p = fabricas.projeto()
    p.regerar_link()
    _acao(admin_client, "acao_revogar_link", p)
    p.refresh_from_db()
    assert p.token_edicao_hash is None
    assert p.token_edicao_gerado_em is None


def test_revogar_link_exige_um_projeto_so(admin_client):
    turma = fabricas.turma()
    a = fabricas.projeto(turma, titulo="A")
    b = fabricas.projeto(turma, titulo="B", ra_hmac=hash_ra("55555"))
    a.regerar_link()
    b.regerar_link()
    resposta = _acao(admin_client, "acao_revogar_link", a, b)
    assert "Selecione exatamente um projeto" in _mensagens(resposta)
    assert Projeto.objects.filter(token_edicao_hash__isnull=False).count() == 2


# --- Histórico das ações ----------------------------------------------------------------


def _historico(projeto):
    return list(
        LogEntry.objects.filter(object_id=str(projeto.pk)).values_list("change_message", flat=True)
    )


def test_acoes_de_moderacao_ficam_no_historico(admin_client, midia):
    turma = fabricas.turma()
    publicado = _completo(turma, titulo="Pub")
    devolvido = fabricas.projeto(
        turma, titulo="Dev", status="em_revisao", motivo_ajustes="Capa borrada", ra_hmac=hash_ra("66666")
    )
    _acao(admin_client, "acao_publicar", publicado)
    _acao(admin_client, "acao_devolver", devolvido)
    assert _historico(publicado) == ["Publicado"]
    assert _historico(devolvido) == ["Devolvido para ajustes: Capa borrada"]


def test_link_regerado_e_revogado_ficam_no_historico_sem_o_token(admin_client):
    p = fabricas.projeto()
    resposta = _acao(admin_client, "acao_regerar_link", p)
    token = _token_da_pagina(resposta)
    _acao(admin_client, "acao_revogar_link", p)
    historico = _historico(p)
    assert sorted(historico) == ["Link de edição regerado", "Link de edição revogado"]
    assert not any(token in m for m in historico)


def test_acao_que_nao_muda_nada_nao_entra_no_historico(admin_client):
    p = fabricas.projeto(status="em_revisao")  # sem motivo: não devolve
    _acao(admin_client, "acao_devolver", p)
    assert _historico(p) == []


# --- Exclusão ---------------------------------------------------------------------------


def test_lista_nao_oferece_apagar_em_lote(admin_client):
    p = fabricas.projeto()
    resposta = admin_client.post(LISTA, {"action": "delete_selected", "_selected_action": [p.pk]})
    assert Projeto.objects.filter(pk=p.pk).exists()
    assert b'value="delete_selected"' not in admin_client.get(LISTA).content
    assert resposta.status_code in (200, 302)


def test_com_a_votacao_aberta_o_projeto_nao_pode_ser_apagado(admin_client):
    edicao = fabricas.edicao()
    p = fabricas.projeto(fabricas.turma(edicao))
    edicao.votacao_aberta_em = timezone.now() - timedelta(minutes=1)
    edicao.save()
    apagar = reverse("admin:cadastro_projeto_delete", args=[p.pk])
    assert admin_client.get(apagar).status_code == 403
    assert admin_client.post(apagar, {"post": "yes"}).status_code == 403
    assert Projeto.objects.filter(pk=p.pk).exists()


def test_votacao_aberta_depois_da_checagem_ainda_impede_apagar(rf, admin_user):
    """Corrida: a votação abre entre has_delete_permission e o delete. O delete_model
    relê a abertura com a linha da edição travada."""
    edicao = fabricas.edicao()
    p = fabricas.projeto(fabricas.turma(edicao))
    edicao.votacao_aberta_em = timezone.now() - timedelta(minutes=1)
    edicao.save()
    requisicao = rf.post("/")
    requisicao.user = admin_user
    with pytest.raises(PermissionDenied):
        ProjetoAdmin(Projeto, site).delete_model(requisicao, p)
    assert Projeto.objects.filter(pk=p.pk).exists()


def test_antes_da_votacao_o_projeto_pode_ser_apagado(admin_client):
    p = fabricas.projeto()
    apagar = reverse("admin:cadastro_projeto_delete", args=[p.pk])
    admin_client.post(apagar, {"post": "yes"})
    assert not Projeto.objects.filter(pk=p.pk).exists()


# --- Edição -----------------------------------------------------------------------------


def _dados_edicao(edicao, **campos):
    dados = {
        "nome": edicao.nome,
        "data_evento": edicao.data_evento.isoformat(),
        "prazo_edicao_0": edicao.prazo_edicao.strftime("%Y-%m-%d"),
        "prazo_edicao_1": edicao.prazo_edicao.strftime("%H:%M:%S"),
        "peso_banca": "0.70",
        "peso_publico": "0.30",
        "ativa": "on" if edicao.ativa else "",
    }
    dados.update(campos)
    return {k: v for k, v in dados.items() if v != ""}


def test_pesos_so_leitura_depois_de_abrir_a_votacao(admin_client):
    edicao = fabricas.edicao()
    url = reverse("admin:cadastro_edicao_change", args=[edicao.pk])
    assert "peso_banca" in admin_client.get(url).context["adminform"].form.fields
    edicao.votacao_aberta_em = timezone.now()
    edicao.save()
    assert "peso_banca" not in admin_client.get(url).context["adminform"].form.fields
    admin_client.post(url, _dados_edicao(edicao, peso_banca="0.80", peso_publico="0.20"), follow=True)
    edicao.refresh_from_db()
    assert str(edicao.peso_banca) == "0.70"


def test_ativar_segunda_edicao_volta_com_erro_legivel(admin_client):
    fabricas.edicao(nome="2026/1", ativa=True)
    outra = fabricas.edicao(nome="2026/2")
    url = reverse("admin:cadastro_edicao_change", args=[outra.pk])
    resposta = admin_client.post(url, _dados_edicao(outra, ativa="on"))
    assert resposta.status_code == 200
    assert "Desative-a antes de ativar outra." in resposta.content.decode()
    assert Edicao.objects.filter(ativa=True).count() == 1


# --- Corrida entre o formulário e as ações ----------------------------------------------


def _no_meio_do_post(monkeypatch, acao):
    """Roda `acao` (outra requisição) depois que o admin já leu o projeto e antes de gravar."""
    original = ProjetoForm.clean

    def clean(self):
        dados = original(self)
        acao(Projeto.objects.get(pk=self.instance.pk))
        return dados

    monkeypatch.setattr(ProjetoForm, "clean", clean)


def test_salvar_o_formulario_nao_ressuscita_link_revogado(admin_client, monkeypatch):
    p = fabricas.projeto()
    p.regerar_link()
    _no_meio_do_post(monkeypatch, lambda outro: outro.revogar_link())
    admin_client.post(_editar(p), _edicao(p, titulo="Título novo"), follow=True)
    p.refresh_from_db()
    assert p.titulo == "Título novo"
    assert p.token_edicao_hash is None and p.token_edicao_gerado_em is None


def test_salvar_o_formulario_nao_desfaz_publicar(admin_client, monkeypatch, midia):
    p = _completo()
    _no_meio_do_post(monkeypatch, lambda outro: outro.publicar())
    dados = _edicao(p, titulo=p.titulo, resumo="Resumo novo", descricao="Descrição")
    admin_client.post(_editar(p), dados, follow=True)
    p.refresh_from_db()
    assert p.resumo == "Resumo novo"
    assert p.status == Projeto.Status.PUBLICADO and p.publicado_em is not None


# --- Formulário aberto antes de outra gravação (parecer do Renan no #60) -----------------

AVISO_VERSAO = "Este projeto mudou depois que você abriu o formulário"


def test_formulario_aberto_antes_nao_regrava_o_texto_que_o_grupo_salvou(admin_client):
    p = fabricas.projeto(descricao="X")
    aberto = _edicao(p, titulo=p.titulo, descricao="X")  # 1. o admin abre com X
    grupo = Projeto.objects.get(pk=p.pk)
    grupo.descricao = "Y"
    grupo.save(update_fields=["descricao", "atualizado_em"])  # 2. o grupo salva Y
    resposta = admin_client.post(_editar(p), {**aberto, "motivo_ajustes": "Capa borrada"})  # 3. envia X
    assert resposta.status_code == 200
    assert AVISO_VERSAO in resposta.content.decode()
    p.refresh_from_db()
    assert p.descricao == "Y" and p.motivo_ajustes == ""


def test_formulario_aberto_antes_de_regerar_o_link_e_recusado(admin_client):
    p = fabricas.projeto()
    aberto = _edicao(p, titulo="Outro título")
    token = Projeto.objects.get(pk=p.pk).regerar_link()
    resposta = admin_client.post(_editar(p), aberto)
    assert AVISO_VERSAO in resposta.content.decode()
    p.refresh_from_db()
    assert p.titulo != "Outro título"
    assert p.token_edicao_hash == hash_token(token)


def test_formulario_sem_versao_e_recusado(admin_client):
    p = fabricas.projeto()
    dados = _edicao(p, titulo="Outro título")
    del dados["versao"]
    resposta = admin_client.post(_editar(p), dados)
    assert AVISO_VERSAO in resposta.content.decode()
    assert Projeto.objects.get(pk=p.pk).titulo != "Outro título"


def test_formulario_traz_a_versao_ao_abrir(admin_client):
    p = fabricas.projeto()
    html = admin_client.get(_editar(p)).content.decode()
    assert f'name="versao" value="{_versao(p)}"' in html
