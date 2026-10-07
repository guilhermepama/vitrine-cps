"""Critérios de aceite "Edição" (specs/02-vitrine-publica.md)."""

import pytest
from django.core.exceptions import ValidationError

from cadastro.models import Curso, Integrante, Projeto
from vitrine import servicos
from vitrine.tests import auxiliares as aux


def url(token):
    return f"/grupo/editar/{token}/"


# --- Link inválido -------------------------------------------------------------


@pytest.mark.django_db
def test_token_inexistente_revogado_e_regerado_dao_o_mesmo_404(client):
    p, antigo = aux.projeto_com_link()
    p.regerar_link()  # o link antigo deixa de valer
    revogado, token_revogado = aux.projeto_com_link(edicao=p.turma.edicao, ra_hmac=aux.hash_ra("7654321"))
    revogado.revogar_link()

    respostas = [client.get(url(t)) for t in ("naoexiste", antigo, token_revogado)]
    assert {r.status_code for r in respostas} == {404}
    assert len({aux.sem_csrf(r.content.decode()) for r in respostas}) == 1


@pytest.mark.django_db
def test_link_antigo_para_de_valer_depois_de_regerar(client):
    p, antigo = aux.projeto_com_link()
    assert client.get(url(antigo)).status_code == 200
    novo = p.regerar_link()
    assert client.get(url(antigo)).status_code == 404
    assert client.get(url(novo)).status_code == 200


# --- Tela editável ---------------------------------------------------------------


@pytest.mark.django_db
def test_get_mostra_o_formulario_sem_o_titulo_editavel(client):
    p, token = aux.projeto_com_link()
    html = client.get(url(token)).content.decode()
    assert 'name="acao" value="salvar"' in html and 'name="acao" value="enviar"' in html
    assert 'name="titulo"' not in html
    assert "Salve o texto antes de enviar imagens" in html


@pytest.mark.django_db
def test_em_ajustes_mostra_o_motivo(client):
    p, token = aux.projeto_com_link()
    p.status = Projeto.Status.AJUSTES
    p.motivo_ajustes = "Troque a capa por uma imagem mais nítida."
    p.save(update_fields=["status", "motivo_ajustes", "atualizado_em"])
    assert "Troque a capa por uma imagem mais nítida." in client.get(url(token)).content.decode()


@pytest.mark.django_db
def test_paginas_do_grupo_tem_os_cabecalhos_de_protecao(client):
    p, token = aux.projeto_com_link()
    for resposta in (client.get(url(token)), client.get(url("naoexiste")), client.get("/grupo/")):
        assert resposta["Referrer-Policy"] == "no-referrer"
        assert resposta["X-Robots-Tag"] == "noindex"
        assert "no-store" in resposta["Cache-Control"]


# --- Salvar e enviar para revisão ----------------------------------------------------


@pytest.mark.django_db
def test_salvar_grava_e_mantem_o_status_mesmo_incompleto(client):
    p, token = aux.projeto_com_link()
    r = client.post(url(token), aux.dados_de_edicao(resumo="", descricao="", integrantes=()), follow=True)
    assert r.status_code == 200
    assert "Rascunho salvo" in r.content.decode()
    p.refresh_from_db()
    assert p.status == Projeto.Status.PRE_CADASTRADO
    html = r.content.decode()
    assert "capa" in html and "resumo" in html  # lista do que falta


@pytest.mark.django_db
def test_salvar_grava_resumo_descricao_e_equipe_em_ordem(client):
    p, token = aux.projeto_com_link()
    dados = aux.dados_de_edicao(integrantes=(("Ana", "Front-end"), ("Bruno", ""), ("Carla", "Pesquisa")))
    client.post(url(token), dados)
    p.refresh_from_db()
    assert p.resumo == "Um resumo do projeto."
    assert [i.nome for i in p.integrantes.all()] == ["Ana", "Bruno", "Carla"]


@pytest.mark.django_db
def test_enviar_sem_pendencias_muda_para_em_revisao(client):
    p, token = aux.projeto_com_link()
    aux.com_capa(p)
    r = client.post(url(token), aux.dados_de_edicao(acao="enviar"), follow=True)
    assert "Enviado para revisão" in r.content.decode()
    p.refresh_from_db()
    assert p.status == Projeto.Status.EM_REVISAO
    assert p.resumo == "Um resumo do projeto." and p.integrantes.count() == 1


@pytest.mark.django_db
def test_enviar_com_pendencias_da_400_e_nao_grava_nada(client):
    p, token = aux.projeto_com_link()  # sem capa
    r = client.post(url(token), aux.dados_de_edicao(acao="enviar"))
    assert r.status_code == 400
    html = r.content.decode()
    assert "O que falta" in html and "capa" in html
    assert "Um resumo do projeto." in html  # o formulário volta com o digitado
    p.refresh_from_db()
    assert p.status == Projeto.Status.PRE_CADASTRADO
    assert p.resumo == "" and p.integrantes.count() == 0


@pytest.mark.django_db
def test_enviar_apagando_o_resumo_no_mesmo_envio_desfaz_tudo(client):
    p, token = aux.projeto_com_link(resumo="Resumo antigo", descricao="Descrição antiga")
    Integrante.objects.create(projeto=p, nome="Ana", ordem=0)
    aux.com_capa(p)
    r = client.post(url(token), aux.dados_de_edicao(resumo="", acao="enviar", integrantes=(("Bia", ""),)))
    assert r.status_code == 400
    p.refresh_from_db()
    assert p.status == Projeto.Status.PRE_CADASTRADO
    assert p.resumo == "Resumo antigo"
    assert [i.nome for i in p.integrantes.all()] == ["Ana"]


@pytest.mark.django_db
def test_acao_desconhecida_da_400(client):
    p, token = aux.projeto_com_link()
    assert client.post(url(token), aux.dados_de_edicao(acao="publicar")).status_code == 400


@pytest.mark.django_db
def test_acao_desconhecida_em_projeto_nao_editavel_da_403(client):
    p, token = aux.projeto_com_link(status=Projeto.Status.EM_REVISAO)
    assert client.post(url(token), aux.dados_de_edicao(acao="xyz")).status_code == 403


@pytest.mark.django_db
def test_salvar_em_ajustes_mantem_o_status(client):
    p, token = aux.projeto_com_link(status=Projeto.Status.AJUSTES, motivo_ajustes="Melhore o resumo.")
    assert client.post(url(token), aux.dados_de_edicao(resumo="Novo resumo")).status_code == 302
    p.refresh_from_db()
    assert p.status == Projeto.Status.AJUSTES and p.resumo == "Novo resumo"


@pytest.mark.django_db
def test_enviar_a_partir_de_ajustes_vai_para_revisao(client):
    p, token = aux.projeto_com_link(status=Projeto.Status.AJUSTES, motivo_ajustes="Melhore o resumo.")
    aux.com_capa(p)
    assert client.post(url(token), aux.dados_de_edicao(acao="enviar")).status_code == 302
    p.refresh_from_db()
    assert p.status == Projeto.Status.EM_REVISAO


@pytest.mark.django_db
def test_salvar_regrava_so_os_campos_do_grupo(client):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    p, token = aux.projeto_com_link()
    with CaptureQueriesContext(connection) as consultas:
        client.post(url(token), aux.dados_de_edicao())
    updates = [c["sql"] for c in consultas.captured_queries if c["sql"].startswith('UPDATE "cadastro_projeto"')]
    assert updates
    for sql in updates:
        for coluna in ("status", "slug", "titulo", "ra_hmac", "token_edicao_hash", "turma_id", "publicado_em"):
            assert f'"{coluna}"' not in sql.split(" WHERE ")[0], (coluna, sql)


def _em_outra_conexao(funcao):
    """Roda `funcao` numa thread com a própria conexão (a votação abre em outro processo)."""
    import threading

    from django.db import connection

    def alvo():
        try:
            funcao()
        finally:
            connection.close()

    return threading.Thread(target=alvo)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("acao", ["salvar", "enviar"])
def test_votacao_aberta_entre_a_leitura_e_a_trava_da_403_explicada_e_nao_grava(client, monkeypatch, acao):
    p, token = aux.projeto_com_link()
    aux.com_capa(p)
    original = servicos.travar_para_edicao

    def abrir_a_votacao_e_travar(pk, tok):
        outra = _em_outra_conexao(lambda: aux.votacao_aberta(p))
        outra.start()
        outra.join()
        return original(pk, tok)

    monkeypatch.setattr(servicos, "travar_para_edicao", abrir_a_votacao_e_travar)
    r = client.post(url(token), aux.dados_de_edicao(acao=acao))
    assert r.status_code == 403
    html = r.content.decode()
    assert "Fale com a coordenação" in html and 'name="acao"' not in html
    p.refresh_from_db()
    assert p.status == Projeto.Status.PRE_CADASTRADO and p.resumo == ""


@pytest.mark.django_db(transaction=True)
def test_a_votacao_so_abre_depois_do_salvar_em_andamento(client, monkeypatch):
    """A `Edicao` fica travada durante o Salvar: a abertura espera, em vez de passar no meio."""
    p, token = aux.projeto_com_link()
    original = servicos.travar_para_edicao
    abertura, ficou_bloqueada = [], []

    def travar_e_tentar_abrir(pk, tok):
        travado = original(pk, tok)
        abertura.append(_em_outra_conexao(lambda: aux.votacao_aberta(p)))
        abertura[0].start()
        abertura[0].join(1)
        ficou_bloqueada.append(abertura[0].is_alive())
        return travado

    monkeypatch.setattr(servicos, "travar_para_edicao", travar_e_tentar_abrir)
    assert client.post(url(token), aux.dados_de_edicao(resumo="Gravado antes da abertura")).status_code == 302
    abertura[0].join(15)
    assert ficou_bloqueada == [True]
    p.refresh_from_db()
    assert p.resumo == "Gravado antes da abertura"
    assert p.turma.edicao.votacao_foi_aberta()  # a abertura concluiu depois do Salvar


def test_travar_a_edicao_antes_do_projeto():
    """Ordem Edicao -> Projeto (a do `Projeto.save()` e do admin): evita deadlock."""
    import inspect

    codigo = inspect.getsource(servicos.travar_para_edicao)
    assert codigo.index("Edicao.objects.select_for_update") < codigo.index("Projeto.objects.select_for_update")


@pytest.mark.django_db(transaction=True)
def test_link_regerado_entre_a_leitura_e_a_gravacao_nao_grava(client, monkeypatch):
    p, token = aux.projeto_com_link()
    original = servicos.travar_para_edicao

    def regerar_antes(pk, tok):
        outra = _em_outra_conexao(lambda: Projeto.objects.get(pk=p.pk).regerar_link())
        outra.start()
        outra.join()
        return original(pk, tok)

    monkeypatch.setattr(servicos, "travar_para_edicao", regerar_antes)
    assert client.post(url(token), aux.dados_de_edicao()).status_code == 404
    p.refresh_from_db()
    assert p.resumo == "" and p.integrantes.count() == 0


@pytest.mark.django_db
def test_tela_somente_leitura_mostra_componente_e_links(client):
    p, token = aux.projeto_com_link(
        status=Projeto.Status.EM_REVISAO,
        componente_origem="PI II",
        link_repositorio="https://github.com/grupo/projeto",
    )
    html = client.get(url(token)).content.decode()
    assert "PI II" in html and "https://github.com/grupo/projeto" in html


@pytest.mark.django_db
def test_titulo_e_slug_nao_mudam_nem_com_campo_titulo_no_post(client):
    p, token = aux.projeto_com_link(titulo="Agenda Escolar")
    client.post(url(token), aux.dados_de_edicao(titulo="Outro nome", slug="outro"))
    p.refresh_from_db()
    assert p.titulo == "Agenda Escolar" and p.slug == "agenda-escolar"


# --- Validações ---------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("link", ["http://exemplo.com/x", "javascript:alert(1)", "ftp://exemplo.com"])
def test_link_que_nao_e_https_e_recusado(client, link):
    p, token = aux.projeto_com_link()
    r = client.post(url(token), aux.dados_de_edicao(link_demo=link))
    assert r.status_code == 400
    p.refresh_from_db()
    assert p.link_demo == "" and p.resumo == ""


@pytest.mark.django_db
def test_link_https_e_aceito(client):
    p, token = aux.projeto_com_link()
    client.post(url(token), aux.dados_de_edicao(link_repositorio="https://github.com/grupo/projeto"))
    p.refresh_from_db()
    assert p.link_repositorio == "https://github.com/grupo/projeto"


@pytest.mark.django_db
def test_etec_so_aceita_o_primeiro_nome_e_fatec_aceita_o_completo(client):
    etec, token_etec = aux.projeto_com_link(unidade=Curso.Unidade.ETEC)
    r = client.post(url(token_etec), aux.dados_de_edicao(integrantes=(("Ana Souza", ""),)))
    assert r.status_code == 400 and etec.integrantes.count() == 0
    assert client.post(url(token_etec), aux.dados_de_edicao(integrantes=(("Ana", ""),))).status_code == 302

    fatec, token_fatec = aux.projeto_com_link(unidade=Curso.Unidade.FATEC, edicao=etec.turma.edicao, ra_hmac=aux.hash_ra("7654321"))
    assert client.post(url(token_fatec), aux.dados_de_edicao(integrantes=(("Ana Souza", ""),))).status_code == 302
    assert fatec.integrantes.get().nome == "Ana Souza"


@pytest.mark.django_db
def test_onze_integrantes_sao_recusados(client):
    p, token = aux.projeto_com_link()
    r = client.post(url(token), aux.dados_de_edicao(integrantes=[(f"Pessoa{i}", "") for i in range(11)]))
    assert r.status_code == 400
    assert p.integrantes.count() == 0


# --- Quando a tela não é editável --------------------------------------------------------


def _nao_editavel(cenario):
    if cenario == "em_revisao":
        return aux.projeto_com_link(status=Projeto.Status.EM_REVISAO)
    if cenario == "publicado":
        return aux.projeto_com_link(status=Projeto.Status.PUBLICADO)
    p, token = aux.projeto_com_link()
    (aux.prazo_vencido if cenario == "prazo" else aux.votacao_aberta)(p)
    return p, token


@pytest.mark.django_db
@pytest.mark.parametrize("cenario", ["em_revisao", "publicado", "prazo", "votacao_aberta"])
def test_tela_vira_somente_leitura_e_post_da_403_sem_gravar(client, cenario):
    p, token = _nao_editavel(cenario)
    leitura = client.get(url(token))
    assert leitura.status_code == 200
    assert 'name="acao"' not in leitura.content.decode()
    r = client.post(url(token), aux.dados_de_edicao())
    assert r.status_code == 403
    p.refresh_from_db()
    assert p.resumo == "" and p.integrantes.count() == 0


@pytest.mark.django_db
def test_validation_error_do_save_no_meio_do_envio_desfaz_e_da_403(client, monkeypatch):
    p, token = aux.projeto_com_link()
    aux.com_capa(p)

    def recusar(_projeto):
        raise ValidationError("A votação desta edição já foi aberta.")

    monkeypatch.setattr(servicos, "enviar_para_revisao", recusar)  # ver também o teste da votação real
    r = client.post(url(token), aux.dados_de_edicao(acao="enviar"))
    assert r.status_code == 403
    p.refresh_from_db()
    assert p.status == Projeto.Status.PRE_CADASTRADO and p.resumo == ""


def test_tela_de_edicao_nao_mostra_o_nome_do_representante(client, db):
    p, token = aux.projeto_com_link(representante_nome="Fulano de Tal da Silva")
    assert "Fulano" not in client.get(url(token)).content.decode()


def test_integrante_de_outro_projeto_no_formset_nao_e_alterado(client, db):
    p, token = aux.projeto_com_link()
    outro, _ = aux.projeto_com_link(edicao=p.turma.edicao, ra_hmac=aux.hash_ra("7654321"))
    alheio = Integrante.objects.create(projeto=outro, nome="Alheio", papel="Original", ordem=0)
    dados = aux.dados_de_edicao(integrantes=(("Invasor", "Trocado"),))
    dados.update({"integrantes-INITIAL_FORMS": "1", "integrantes-0-id": str(alheio.pk)})
    client.post(url(token), dados)
    alheio.refresh_from_db()
    assert (alheio.nome, alheio.papel, alheio.projeto_id) == ("Alheio", "Original", outro.pk)
    assert not p.integrantes.filter(nome="Invasor", pk=alheio.pk).exists()
