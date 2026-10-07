"""Critérios de aceite "Reivindicação" (specs/02-vitrine-publica.md)."""

import logging
import threading
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from cadastro.models import Projeto
from cadastro.seguranca import hash_token
from vitrine import servicos
from vitrine.tests import auxiliares as aux

URL = "/grupo/"


def _recusado(client, ra, **extra):
    return client.post(URL, {"ra": ra}, **extra)


def _contadores(client):
    """(falhas do IP do cliente de teste, falhas globais) na janela atual."""
    request = client.get(URL).wsgi_request
    return (
        cache.get(servicos.chave_falhas_ip(request), 0),
        cache.get(servicos.chave_falhas_global(), 0),
    )


@pytest.mark.django_db
def test_ra_valido_mostra_o_link_e_grava_so_o_hash(client):
    p = aux.projeto_reivindicavel()
    r = client.post(URL, {"ra": aux.RA})
    assert r.status_code == 200
    html = r.content.decode()
    assert "/grupo/editar/" in html
    p.refresh_from_db()
    assert p.reivindicado_em is not None and p.token_edicao_gerado_em is not None
    token = html.split("/grupo/editar/")[1].split('"')[0].strip("/")
    assert p.token_edicao_hash == hash_token(token)
    assert "no-store" in r["Cache-Control"]


@pytest.mark.django_db
def test_formulario_avisa_que_o_link_aparece_uma_vez(client):
    html = client.get(URL).content.decode()
    assert "uma única vez" in html


@pytest.mark.django_db
def test_pagina_do_link_tem_link_completo_copiar_e_abrir(client, settings):
    settings.URL_PUBLICA = "https://vitrine.exemplo.com.br"
    aux.projeto_reivindicavel()
    html = client.post(URL, {"ra": aux.RA}).content.decode()
    link = "https://vitrine.exemplo.com.br/grupo/editar/"
    assert f'value="{link}' in html
    assert f'href="{link}' in html
    assert 'id="copiar"' in html
    assert "Abrir edição do projeto" in html
    assert "só esta vez" in html


@pytest.mark.django_db
def test_ra_com_pontuacao_reivindica_o_mesmo_projeto(client):
    p = aux.projeto_reivindicavel(ra="1234567")
    r = client.post(URL, {"ra": "123.456-7"})
    assert r.status_code == 200
    p.refresh_from_db()
    assert p.reivindicado_em is not None


def _cenario(nome):
    """Monta um estado em que a reivindicação deve ser recusada; devolve o RA a digitar."""
    if nome == "inexistente":
        return "9999999"
    if nome == "malformado":
        return "abc"
    if nome == "vazio":
        return ""
    if nome == "ja_reivindicado":
        p = aux.projeto_reivindicavel(ra="1111111")
        p.reivindicado_em = timezone.now()
        p.save(update_fields=["reivindicado_em", "atualizado_em"])
        return "1111111"
    if nome == "outra_edicao":
        aux.projeto_reivindicavel(ra="2222222", edicao=aux.nova_edicao(ativa=False))
        return "2222222"
    if nome == "prazo_vencido":
        p = aux.projeto_reivindicavel(ra="3333333")
        aux.prazo_vencido(p)
        return "3333333"
    if nome == "votacao_aberta":
        p = aux.projeto_reivindicavel(ra="4444444")
        aux.votacao_aberta(p)
        return "4444444"
    if nome == "fora_de_pre_cadastrado":
        p = aux.projeto_reivindicavel(ra="5555555")
        p.status = Projeto.Status.EM_REVISAO
        p.save(update_fields=["status", "atualizado_em"])
        return "5555555"
    raise AssertionError(nome)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "cenario",
    ["inexistente", "malformado", "vazio", "ja_reivindicado", "outra_edicao", "prazo_vencido", "votacao_aberta", "fora_de_pre_cadastrado"],
)
def test_respostas_de_falha_sao_identicas(client, cenario):
    ra = _cenario(cenario)
    referencia = _recusado(client, "0000000")  # RA que não existe: a resposta de referência
    resposta = _recusado(client, ra)
    assert resposta.status_code == referencia.status_code == 400
    assert aux.sem_csrf(resposta.content.decode()) == aux.sem_csrf(referencia.content.decode())


@pytest.mark.django_db
def test_pagina_de_erro_nao_repete_o_ra(client):
    r = _recusado(client, "9876543")
    assert "9876543" not in r.content.decode()


@pytest.mark.django_db
def test_recarregar_o_post_depois_do_sucesso_nao_mostra_outro_link(client):
    aux.projeto_reivindicavel()
    assert client.post(URL, {"ra": aux.RA}).status_code == 200
    segunda = client.post(URL, {"ra": aux.RA})
    assert segunda.status_code == 400
    assert "/grupo/editar/" not in segunda.content.decode()


@pytest.mark.django_db(transaction=True)
def test_dois_posts_simultaneos_emitem_um_link_so():
    aux.projeto_reivindicavel()
    cache.clear()
    resultados = []
    largada = threading.Barrier(2)

    def tentar():
        try:
            largada.wait(5)
            resultados.append(servicos.reivindicar(aux.RA))
        finally:
            connection.close()

    threads = [threading.Thread(target=tentar) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(r is None for r in resultados) == [False, True]


@pytest.mark.django_db
def test_depois_de_50_falhas_do_mesmo_ip_a_proxima_e_429(client):
    for _ in range(servicos.LIMITE_FALHAS_POR_IP):
        assert _recusado(client, "9999999").status_code == 400
    r = _recusado(client, "9999999")
    assert r.status_code == 429


@pytest.mark.django_db
def test_sucesso_nao_consome_o_limite(client):
    aux.projeto_reivindicavel()
    for _ in range(5):
        _recusado(client, "9999999")
    ip, glob = _contadores(client)
    assert ip == glob == 5
    assert client.post(URL, {"ra": aux.RA}).status_code == 200
    assert _contadores(client) == (ip, glob)


@pytest.mark.django_db
def test_limite_global_vale_para_qualquer_ip(client):
    cache.set(servicos.chave_falhas_global(), servicos.LIMITE_FALHAS_GLOBAL, 60)
    assert _recusado(client, "9999999", REMOTE_ADDR="198.51.100.7").status_code == 429


@pytest.mark.django_db
def test_falhas_de_ips_diferentes_somam_na_chave_global(client):
    cache.set(servicos.chave_falhas_global(), servicos.LIMITE_FALHAS_GLOBAL - 2, 60)
    # A 999ª e a 1.000ª falhas (IPs distintos) ainda são processadas (400)...
    assert _recusado(client, "9999999", REMOTE_ADDR="198.51.100.1").status_code == 400
    assert cache.get(servicos.chave_falhas_global()) == servicos.LIMITE_FALHAS_GLOBAL - 1
    assert _recusado(client, "9999999", REMOTE_ADDR="198.51.100.2").status_code == 400
    assert cache.get(servicos.chave_falhas_global()) == servicos.LIMITE_FALHAS_GLOBAL
    # ... e a próxima, de um IP novo, já esbarra no limite global.
    assert _recusado(client, "9999999", REMOTE_ADDR="198.51.100.3").status_code == 429


@pytest.mark.django_db
def test_enderecos_ipv6_do_mesmo_64_contam_juntos(client):
    for i in range(servicos.LIMITE_FALHAS_POR_IP):
        _recusado(client, "9999999", REMOTE_ADDR=f"2001:db8:0:0::{i + 1:x}")
    assert _recusado(client, "9999999", REMOTE_ADDR="2001:db8:0:0:ffff::1").status_code == 429
    assert _recusado(client, "9999999", REMOTE_ADDR="2001:db8:0:1::1").status_code == 400  # outro /64


@pytest.mark.django_db
def test_a_chave_do_ip_expira_e_nao_traz_o_ip_em_claro(client):
    _recusado(client, "9999999", REMOTE_ADDR="203.0.113.9")
    with connection.cursor() as cursor:
        cursor.execute("SELECT cache_key, expires FROM cache_django WHERE cache_key LIKE %s", ["%rl:grupo%"])
        linhas = cursor.fetchall()
    assert linhas
    assert all("203.0.113.9" not in chave for chave, _ in linhas)
    # Prazo explícito, maior que o padrão de 300 s do cache (a janela do IP é de 10 min).
    assert all(expira > timezone.now() + timedelta(minutes=15) for _, expira in linhas)


@pytest.mark.django_db
def test_ra_nao_aparece_no_log_nem_na_resposta_de_erro(client, caplog):
    aux.projeto_reivindicavel()
    with caplog.at_level(logging.DEBUG):
        r = _recusado(client, "7654321")
        ok = client.post(URL, {"ra": aux.RA})
    assert "7654321" not in caplog.text and aux.RA not in caplog.text
    assert "7654321" not in r.content.decode()
    assert aux.RA not in ok.content.decode()


@pytest.mark.django_db
def test_ra_em_claro_nao_fica_no_banco(client):
    p = aux.projeto_reivindicavel()
    _recusado(client, "7654321")
    client.post(URL, {"ra": aux.RA})
    textos = [
        str(valor)
        for valor in Projeto.objects.filter(pk=p.pk).values().get().values()
        if valor is not None
    ]
    with connection.cursor() as cursor:
        cursor.execute("SELECT cache_key, value FROM cache_django")
        textos += [f"{chave} {valor}" for chave, valor in cursor.fetchall()]
    assert textos
    assert not any(aux.RA in t or "7654321" in t for t in textos)


@pytest.mark.django_db
def test_projeto_so_e_reivindicado_uma_vez_e_fica_com_status_pre_cadastrado(client):
    p = aux.projeto_reivindicavel()
    client.post(URL, {"ra": aux.RA})
    p.refresh_from_db()
    assert p.status == Projeto.Status.PRE_CADASTRADO


def test_a_rota_e_o_nome_da_pagina_do_grupo():
    assert reverse("vitrine:grupo") == "/grupo/"


@pytest.mark.django_db
def test_dois_projetos_com_o_mesmo_ra_na_edicao_nao_sao_reivindicados(client, caplog):
    """A unicidade do RA só vale em clean(): se houver duplicata, ninguém reivindica."""
    from cadastro.models import Projeto
    from cadastro.tests import fabricas

    p1 = aux.projeto_reivindicavel()
    outra_turma = fabricas.turma(p1.turma.edicao, fabricas.curso(sigla="OUT"))
    # Duplicata criada pulando o clean() (como uma carga direta faria).
    Projeto.objects.bulk_create(
        [Projeto(turma=outra_turma, titulo="Outro", representante_nome="Zé", ra_hmac=p1.ra_hmac, slug="outro")]
    )
    with caplog.at_level(logging.WARNING):
        r = client.post(URL, {"ra": aux.RA})
    assert r.status_code == 400
    assert Projeto.objects.filter(reivindicado_em__isnull=False).count() == 0
    assert "Mais de um projeto" in caplog.text and aux.RA not in caplog.text
    assert cache.get(servicos.chave_falhas_global(), 0) == 1  # conta como falha


@pytest.mark.django_db
def test_link_de_edicao_usa_a_origem_publica(client, settings):
    settings.URL_PUBLICA = "https://vitrine.exemplo.com.br"
    aux.projeto_reivindicavel()
    html = client.post(URL, {"ra": aux.RA}).content.decode()
    assert 'value="https://vitrine.exemplo.com.br/grupo/editar/' in html


@pytest.mark.django_db
def test_ra_malformado_nao_consulta_projeto(client):
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as consultas:
        r = client.post(URL, {"ra": "abc"})
    assert r.status_code == 400
    assert not any("cadastro_projeto" in c["sql"] for c in consultas.captured_queries)
