"""Ficha da banca para imprimir (spec 06, fatia 4)."""

import re

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone

from banca.models import Criterio, Jurado
from banca.sinais import GRUPO_DIGITACAO
from banca.tests import fabricas
from cadastro.models import Integrante, Projeto
from cadastro.seguranca import hash_ra
from cadastro.tests import fabricas as cadastro
from votacao.servicos import abrir_votacao

pytestmark = pytest.mark.django_db
User = get_user_model()
PUBLICADO = Projeto.Status.PUBLICADO
PROVISORIA = "Lista provisória: projetos podem mudar até a abertura da votação"
SEM_PROJETO = "Nenhum projeto publicado nas turmas deste jurado"
ESCALA = "0 a 10, uma casa decimal (ex.: 7,5)"


def _ficha(jurado):
    return reverse("admin:banca_jurado_ficha", args=[jurado.pk])


def _fichas(edicao):
    return reverse("admin:banca_jurado_fichas_edicao", args=[edicao.pk])


def _staff(username, *permissoes, staff=True):
    usuario = User.objects.create_user(username, f"{username}@example.com", "senha-forte-123", is_staff=staff)
    for codigo in permissoes:
        usuario.user_permissions.add(Permission.objects.get(content_type__app_label="banca", codename=codigo))
    return usuario


@pytest.fixture
def impressor(client):
    client.force_login(_staff("coord", "imprimir_ficha"))
    return client


@pytest.fixture
def cenario():
    """Edição sem votação aberta; jurado em duas turmas, com projetos em vários
    estados e uma turma que não é dele."""
    edicao = cadastro.edicao()
    dsm = cadastro.turma(edicao, cadastro.curso("DSM"))
    gtur = cadastro.turma(edicao, cadastro.curso("GTUR"))
    alheia = cadastro.turma(edicao, cadastro.curso("ADS"))
    Criterio.objects.create(edicao=edicao, nome="Inovação", apoio="A solução é nova?", ordem=2)
    Criterio.objects.create(edicao=edicao, nome="Impacto social", apoio="Problema real?", ordem=1)
    projetos = {
        "zebra": cadastro.projeto(dsm, titulo="Zebra Digital", status=PUBLICADO),
        "abelha": cadastro.projeto(dsm, titulo="Abelha Conectada", status=PUBLICADO),
        "turismo": cadastro.projeto(gtur, titulo="Rota das Águas", status=PUBLICADO),
        "revisao": cadastro.projeto(dsm, titulo="Projeto Em Revisão", status=Projeto.Status.EM_REVISAO),
        "pre": cadastro.projeto(dsm, titulo="Projeto Pré-cadastrado"),
        "alheio": cadastro.projeto(alheia, titulo="Projeto Alheio", status=PUBLICADO),
    }
    jurado = fabricas.jurado(edicao, dsm, nome="Ana Jurada")
    jurado.turmas.add(gtur)
    return edicao, jurado, projetos


# --- Conteúdo ---------------------------------------------------------------------------


def test_lista_so_publicados_das_turmas_do_jurado_por_turma_e_titulo(impressor, cenario):
    edicao, jurado, projetos = cenario
    resposta = impressor.get(_ficha(jurado))
    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert edicao.nome in html and "Ana Jurada" in html and ESCALA in html
    for chave in ("revisao", "pre", "alheio"):
        assert projetos[chave].titulo not in html
    ordem = ["DSM —", projetos["abelha"].titulo, projetos["zebra"].titulo, "GTUR —", projetos["turismo"].titulo]
    posicoes = [html.index(texto) for texto in ordem]
    assert posicoes == sorted(posicoes)
    for projeto in (projetos["abelha"], projetos["zebra"], projetos["turismo"]):
        assert f"<td>{projeto.pk}</td><td>{projeto.titulo}</td>" in html


def test_uma_coluna_em_branco_por_criterio_na_ordem(impressor, cenario):
    _, jurado, projetos = cenario
    html = impressor.get(_ficha(jurado)).content.decode()
    assert html.index("1. Impacto social</th>") < html.index("2. Inovação</th>")
    assert html.index("Impacto social</strong> — Problema real?") < html.index("Inovação</strong> — A solução é nova?")
    linha = re.search(rf"<tr><td>{projetos['abelha'].pk}</td>.*?</tr>", html).group(0)
    assert linha.count('<td class="nota"></td>') == 2


def test_assinatura_data_e_hora_de_geracao(impressor, cenario):
    _, jurado, _ = cenario
    html = impressor.get(_ficha(jurado)).content.decode()
    assert "Assinatura:" in html and "Data:" in html
    hoje = timezone.localtime().strftime("%d/%m/%Y")
    assert re.search(rf"Gerada em {hoje} \d\d:\d\d", html)


def test_sem_dados_pessoais_nem_links(impressor, cenario):
    _, jurado, projetos = cenario
    projeto = projetos["abelha"]
    projeto.representante_nome = "Fulana Representante"
    projeto.ra_hmac = hash_ra("9876543210987")
    projeto.token_edicao_hash = "f" * 64
    projeto.save()
    Integrante.objects.create(projeto=projeto, nome="Beltrano Integrante", papel="Designer")
    html = impressor.get(_ficha(jurado)).content.decode()
    assert projeto.titulo in html
    for proibido in ("Fulana Representante", "Maria Teste", "9876543210987", projeto.ra_hmac, "f" * 64,
                     "Beltrano Integrante", "Designer", projeto.slug, "<a ", "href"):
        assert proibido not in html


def test_aviso_de_lista_provisoria_so_antes_de_abrir(impressor, cenario):
    edicao, jurado, _ = cenario
    assert PROVISORIA in impressor.get(_ficha(jurado)).content.decode()
    assert PROVISORIA in impressor.get(_fichas(edicao)).content.decode()
    assert abrir_votacao(edicao.pk) is None
    assert PROVISORIA not in impressor.get(_ficha(jurado)).content.decode()
    assert PROVISORIA not in impressor.get(_fichas(edicao)).content.decode()


def test_jurado_sem_turma_mostra_a_mensagem(impressor, cenario):
    edicao, _, _ = cenario
    sozinho = Jurado.objects.create(edicao=edicao, nome="Sem Turma")
    resposta = impressor.get(_ficha(sozinho))
    assert resposta.status_code == 200 and SEM_PROJETO in resposta.content.decode()


def test_jurado_com_turma_sem_publicado_mostra_a_mensagem(impressor, cenario):
    edicao, _, _ = cenario
    vazia = cadastro.turma(edicao, cadastro.curso("MEC"))
    cadastro.projeto(vazia, titulo="Ainda Em Revisão", status=Projeto.Status.EM_REVISAO)
    resposta = impressor.get(_ficha(fabricas.jurado(edicao, vazia, nome="Bia")))
    html = resposta.content.decode()
    assert resposta.status_code == 200 and SEM_PROJETO in html and "Ainda Em Revisão" not in html


def test_com_projeto_nao_mostra_a_mensagem(impressor, cenario):
    _, jurado, _ = cenario
    assert SEM_PROJETO not in impressor.get(_ficha(jurado)).content.decode()


def test_rota_da_edicao_uma_ficha_por_jurado_com_quebra_de_pagina(impressor, cenario):
    edicao, jurado, projetos = cenario
    Jurado.objects.create(edicao=edicao, nome="Bia Jurada")
    outra = cadastro.edicao(nome="Ensaio 2026/2")
    Jurado.objects.create(edicao=outra, nome="Carlos de Outra Edição")
    resposta = impressor.get(_fichas(edicao))
    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert html.count('<section class="ficha">') == 2
    assert html.index("Ana Jurada") < html.index("Bia Jurada")
    assert "Carlos de Outra Edição" not in html
    assert ".ficha + .ficha { break-before: page; page-break-before: always; }" in html
    assert "@page { size: A4;" in html
    secao_bia = html[html.index("Bia Jurada"):]
    assert SEM_PROJETO in secao_bia and projetos["abelha"].titulo not in secao_bia


def test_edicao_sem_jurados(impressor):
    edicao = cadastro.edicao()
    resposta = impressor.get(_fichas(edicao))
    assert resposta.status_code == 200 and "Nenhum jurado cadastrado nesta edição." in resposta.content.decode()


def test_paginas_sem_script(impressor, cenario):
    edicao, jurado, _ = cenario
    for url in (_ficha(jurado), _fichas(edicao)):
        assert "<script" not in impressor.get(url).content.decode().lower()


# --- Consultas --------------------------------------------------------------------------


def _consultas(client, url):
    with CaptureQueriesContext(connection) as capturadas:
        assert client.get(url).status_code == 200
    return len(capturadas)


def test_numero_fixo_de_consultas(impressor):
    pequena, turma_p, _ = fabricas.cenario(criterios=1, projetos=1, nome="Pequena", sigla="P")
    um = fabricas.jurado(pequena, turma_p)
    grande, turma_g, _ = fabricas.cenario(criterios=6, projetos=30, nome="Grande", sigla="G")
    outra = cadastro.turma(grande, cadastro.curso("G2"))
    for i in range(20):
        cadastro.projeto(outra, titulo=f"Outro {i}", status=PUBLICADO)
    varios = [fabricas.jurado(grande, turma_g, nome=f"Jurado {i}") for i in range(8)]
    for jurado in varios:
        jurado.turmas.add(outra)
    impressor.get(_ficha(um))  # aquece sessão e caches
    assert _consultas(impressor, _ficha(um)) == _consultas(impressor, _ficha(varios[0]))
    assert _consultas(impressor, _fichas(pequena)) == _consultas(impressor, _fichas(grande))


# --- Permissões -------------------------------------------------------------------------


def test_anonimo_vai_para_o_login(client, cenario):
    edicao, jurado, _ = cenario
    for url in (_ficha(jurado), _fichas(edicao)):
        resposta = client.get(url)
        assert resposta.status_code == 302 and resposta["Location"].startswith(reverse("admin:login"))


def test_nao_staff_com_permissao_vai_para_o_login(client, cenario):
    edicao, jurado, _ = cenario
    client.force_login(_staff("aluno", "imprimir_ficha", staff=False))
    for url in (_ficha(jurado), _fichas(edicao)):
        resposta = client.get(url)
        assert resposta.status_code == 302 and resposta["Location"].startswith(reverse("admin:login"))


def test_staff_sem_permissao_recebe_403(client, cenario):
    edicao, jurado, _ = cenario
    client.force_login(_staff("renan", "concluir_conferencia"))
    for url in (_ficha(jurado), _fichas(edicao), reverse("admin:banca_jurado_ficha", args=[999999])):
        resposta = client.get(url)
        assert resposta.status_code == 403
        assert "no-store" in resposta["Cache-Control"]


def test_grupo_de_digitacao_recebe_403(client, cenario):
    edicao, jurado, _ = cenario
    usuario = _staff("barbara")
    usuario.groups.add(Group.objects.get(name=GRUPO_DIGITACAO))
    client.force_login(usuario)
    for url in (_ficha(jurado), _fichas(edicao)):
        assert client.get(url).status_code == 403


def test_staff_com_permissao_e_superusuario_abrem(client, impressor, cenario):
    edicao, jurado, _ = cenario
    for url in (_ficha(jurado), _fichas(edicao)):
        resposta = impressor.get(url)
        assert resposta.status_code == 200 and "no-store" in resposta["Cache-Control"]
    client.force_login(User.objects.create_superuser("super", "s@example.com", "senha-forte-123"))
    assert client.get(_ficha(jurado)).status_code == 200


def test_inexistente_404(impressor):
    assert impressor.get(reverse("admin:banca_jurado_ficha", args=[999999])).status_code == 404
    assert impressor.get(reverse("admin:banca_jurado_fichas_edicao", args=[999999])).status_code == 404


def test_rotas_so_aceitam_get(impressor, cenario):
    edicao, jurado, _ = cenario
    assert impressor.post(_ficha(jurado)).status_code == 405
    assert impressor.post(_fichas(edicao)).status_code == 405


def test_rotas_vem_antes_das_padrao():
    # O `<path:object_id>/` do admin não pode capturá-las.
    assert resolve("/admin/banca/jurado/7/ficha/").url_name == "banca_jurado_ficha"
    assert resolve("/admin/banca/jurado/edicao/3/fichas/").url_name == "banca_jurado_fichas_edicao"


# --- Links no admin do jurado ------------------------------------------------------------


def test_tela_do_jurado_tem_links_da_ficha(client, cenario):
    edicao, jurado, _ = cenario
    client.force_login(User.objects.create_superuser("super", "s@example.com", "senha-forte-123"))
    html = client.get(reverse("admin:banca_jurado_change", args=[jurado.pk])).content.decode()
    assert f'href="{_ficha(jurado)}"' in html and f'href="{_fichas(edicao)}"' in html


def test_digitacao_nao_ve_links_da_ficha(client, cenario):
    _, jurado, _ = cenario
    usuario = _staff("barbara")
    usuario.groups.add(Group.objects.get(name=GRUPO_DIGITACAO))
    client.force_login(usuario)
    resposta = client.get(reverse("admin:banca_jurado_change", args=[jurado.pk]))
    assert resposta.status_code == 200 and _ficha(jurado) not in resposta.content.decode()
