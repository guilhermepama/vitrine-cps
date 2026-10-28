"""Caminho crítico do mapa do evento (spec 08)."""

import re

import pytest
from django.core.management import call_command
from django.db import IntegrityError
from django.test.utils import CaptureQueriesContext
from django.db import connection

from cadastro.models import Projeto
from cadastro.tests import fabricas
from mapa import planta
from mapa.models import Local

pytestmark = pytest.mark.django_db

ROTAS_DE_VOTO = re.compile(r"""(href|action|src)=["'][^"']*/(entrar|estacao|votar|votos|visitantes)""")


def _edicao_semeada(**opts):
    edicao = fabricas.edicao(ativa=True)
    call_command("semear_mapa", **opts)
    return edicao


def _publicado(edicao, titulo="Agenda Escolar", **campos):
    turma = fabricas.turma(edicao, fabricas.curso(sigla=f"C{Projeto.objects.count()}"))
    campos.setdefault("status", Projeto.Status.PUBLICADO)
    return fabricas.projeto(turma, titulo=titulo, **campos)


# --- Planta -----------------------------------------------------------------------


def test_planta_tem_os_pontos_da_spec():
    pontos = planta.pontos()
    por_tipo = {}
    for p in pontos:
        por_tipo[p.tipo] = por_tipo.get(p.tipo, 0) + 1
    assert por_tipo == {"estande": 26, "sala": 18, "servico": 8, "estacao": 4, "entrada": 1}
    assert len({p.codigo for p in pontos}) == len(pontos)


def test_retrato_e_a_paisagem_girada_com_a_entrada_embaixo_e_o_lado_a_a_direita():
    por = planta.por_codigo()
    entrada = por["entrada"].em_retrato()
    assert entrada.y + entrada.h == pytest.approx(planta.LARGURA)
    a1, b1 = por["a01"].em_retrato(), por["b01"].em_retrato()
    assert a1.x > b1.x  # fileira A à direita de quem entra
    assert a1.y > por["a12"].em_retrato().y  # numeração cresce a partir da entrada (embaixo)


def test_letras_das_fileiras_mudam_so_o_rotulo():
    padrao, de = planta.por_codigo(), planta.por_codigo(("D", "E"))
    assert padrao["a01"].rotulo == "A1" and de["a01"].rotulo == "D1"
    assert padrao["b14"].rotulo == "B14" and de["b14"].rotulo == "E14"


# --- Semeadura ----------------------------------------------------------------------


def test_semear_cria_os_pontos_da_edicao_ativa_e_nao_duplica():
    edicao = _edicao_semeada()
    assert Local.objects.filter(edicao=edicao).count() == 57
    Local.objects.filter(edicao=edicao, codigo="sala-a-01").update(rotulo="Sala 12", nome="Robótica")
    call_command("semear_mapa")
    assert Local.objects.filter(edicao=edicao).count() == 57
    assert Local.objects.get(edicao=edicao, codigo="sala-a-01").nome == "Robótica"


def test_semear_com_fileiras_d_e():
    edicao = _edicao_semeada(fileiras="D,E")
    rotulos = set(Local.objects.filter(edicao=edicao, tipo="estande").values_list("rotulo", flat=True))
    assert {"D1", "D12", "E1", "E14"} <= rotulos and "A1" not in rotulos


def test_projeto_em_um_estande_so():
    edicao = _edicao_semeada()
    projeto = _publicado(edicao)
    Local.objects.filter(edicao=edicao, codigo="a01").update(projeto=projeto)
    with pytest.raises(IntegrityError):
        Local.objects.filter(edicao=edicao, codigo="a02").update(projeto=projeto)


# --- Página -----------------------------------------------------------------------


def test_mapa_sem_edicao_responde_com_a_planta_vazia(client):
    resposta = client.get("/mapa/")
    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "<title>Mapa do evento — Vitrine Fatec</title>" in html
    assert "Mapa em montagem" in html
    assert html.count('class="mapa__svg ') == 2  # paisagem e retrato


def test_estande_com_projeto_publicado_entra_na_lista_com_link(client):
    edicao = _edicao_semeada()
    publicado = _publicado(edicao, "Horta Inteligente")
    rascunho = _publicado(edicao, "Ainda em Revisão", status=Projeto.Status.EM_REVISAO)
    Local.objects.filter(edicao=edicao, codigo="a03").update(projeto=publicado)
    Local.objects.filter(edicao=edicao, codigo="b02").update(projeto=rascunho)
    html = client.get("/mapa/").content.decode()
    assert f'href="/projeto/{publicado.slug}/"' in html and "Horta Inteligente" in html
    assert "Ainda em Revisão" not in html
    assert "Mapa em montagem" not in html


def test_sala_fechada_nao_mostra_a_atracao_e_a_aberta_mostra(client):
    edicao = _edicao_semeada()
    Local.objects.filter(edicao=edicao, codigo="sala-a-01").update(nome="Oficina de drones", aberta=True)
    Local.objects.filter(edicao=edicao, codigo="sala-a-02").update(nome="Laboratório secreto", aberta=False)
    Local.objects.filter(edicao=edicao, codigo="biblioteca").update(nome="Exposição de TCCs")
    html = client.get("/mapa/").content.decode()
    assert "Oficina de drones" in html and "mp-sala--atracao" in html
    assert "Laboratório secreto" not in html and "mp-sala--fechada" in html
    assert "Exposição de TCCs" in html
    assert "Banheiro feminino" not in html.split("Salas e atrações")[1]  # serviço sem atração fica fora da lista


def test_aqui_marca_a_estacao_e_valor_invalido_e_ignorado(client):
    _edicao_semeada()
    html = client.get("/mapa/?aqui=qr-02").content.decode()
    assert "Você está aqui" in html and "mp-aqui" in html and "Secretaria" in html
    for ruim in ("qr-99", "<script>", "x" * 40, "../"):
        resposta = client.get("/mapa/", {"aqui": ruim})
        assert resposta.status_code == 200
        assert "mp-aqui" not in resposta.content.decode()


def test_sem_estilo_inline_nem_caminho_de_voto(client):
    edicao = _edicao_semeada()
    Local.objects.filter(edicao=edicao, codigo="a01").update(projeto=_publicado(edicao))
    html = client.get("/mapa/?aqui=qr-01").content.decode()
    assert "style=" not in html
    assert not ROTAS_DE_VOTO.search(html)


def test_numero_de_queries_nao_cresce_com_os_projetos(client):
    edicao = _edicao_semeada()
    for codigo in ("a01", "a02", "b01"):
        Local.objects.filter(edicao=edicao, codigo=codigo).update(projeto=_publicado(edicao, f"P {codigo}"))
    with CaptureQueriesContext(connection) as antes:
        client.get("/mapa/")
    for codigo in ("b02", "b03", "a05", "a06"):
        Local.objects.filter(edicao=edicao, codigo=codigo).update(projeto=_publicado(edicao, f"P {codigo}"))
    with CaptureQueriesContext(connection) as depois:
        client.get("/mapa/")
    assert len(antes) == len(depois)
