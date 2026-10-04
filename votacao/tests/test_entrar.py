"""Emissão do token em GET /entrar — fatia F4 (specs/03-credenciamento-votacao.md).

Critérios de aceite fechados aqui (citados em cada bloco):
- Emissão e janela: URL capturada expira; re-scan devolve o mesmo token;
  cookie que não é UUID → token novo sem 500; matriz de `w`/`sig` com corpo
  idêntico; agora − 90s / + 5s aceito, − 91s / + 6s recusado; votação
  encerrada recusa.
- Rate limit: 21ª no mesmo bloco; outra estação no mesmo bloco passa; 301ª
  do mesmo IP; estouro com corpo idêntico e sem token; forjadas não contam;
  chave do IP = HMAC, sem o IP em claro, expira em 10 min; IP só por
  `ip_do_cliente`/`chave_ip`; contadores no DatabaseCache.
- Isolamento: re-scan com cookie do ensaio emite token novo; o do ensaio
  continua intacto.
"""

import ast
import re
import uuid
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import pytest
from django.core.cache import caches
from django.core.management import call_command
from django.db import connection
from django.test import Client
from django.utils import timezone

from cadastro.seguranca import chave_ip
from cadastro.tests import fabricas as cadastro
from votacao import limite
from votacao.assinatura import assinar
from votacao.liberacao import COOKIE_CADASTRO, valor_do_cookie
from votacao.models import Token
from votacao.servicos import abrir_votacao, encerrar_votacao
from votacao.tests import fabricas

pytestmark = pytest.mark.django_db

ROTA = "/entrar"
AGORA = 1_793_000_000  # 2026-10-26, horário fixo dos testes
IP_FICTICIO = "203.0.113.7"


@pytest.fixture(autouse=True)
def relogio():
    with mock.patch("votacao.assinatura.agora", return_value=AGORA) as fixo:
        yield fixo


@pytest.fixture(autouse=True)
def tabela_de_cache():
    call_command("createcachetable", verbosity=0)
    caches["default"].clear()


def _abrir(edicao):
    assert abrir_votacao(edicao.pk) is None
    edicao.refresh_from_db()
    return edicao


@pytest.fixture
def evento():
    return _abrir(cadastro.edicao())


@pytest.fixture
def estacao(evento):
    return fabricas.estacao(evento)


def _ensaio():
    return cadastro.edicao(nome="Ensaio 2026/2", data_evento=date(2026, 10, 22))


def _params(estacao_id, ts=AGORA):
    return {"w": f"{estacao_id}:{ts}", "sig": assinar(estacao_id, ts)}


def _entrar(estacao_id, ts=AGORA, client=None, ip=IP_FICTICIO, **extra):
    return (client or Client()).get(ROTA, _params(estacao_id, ts), REMOTE_ADDR=ip, **extra)


@pytest.fixture
def corpo_qr_expirado():
    """Corpo de referência: assinatura inválida (só caracteres válidos)."""
    resposta = Client().get(ROTA, {"w": f"1:{AGORA}", "sig": "0" * 64})
    assert resposta.status_code == 400
    return resposta.content


def _emitido(resposta):
    assert resposta.status_code == 200
    cookie = resposta.cookies["token"]
    token = Token.objects.get(pk=cookie.value)
    assert cookie["httponly"] and cookie["secure"] and cookie["samesite"] == "Lax"
    assert cookie["max-age"] == 24 * 60 * 60
    return token


def _destino(resposta):
    return re.search(r'id="destino"[^>]*>"([^"]+)"', resposta.content.decode())[1]


# --- Emissão --------------------------------------------------------------------


def test_emite_token_da_estacao_e_manda_para_o_formulario(client, estacao):
    resposta = _entrar(estacao.pk, client=client)
    token = _emitido(resposta)
    assert token.estacao == estacao
    assert _destino(resposta) == "/visitantes"
    html = resposta.content.decode()
    # json_script, nunca interpolado em JS (A7); sem cache do token (never_cache).
    assert f'<script id="token" type="application/json">"{token.pk}"</script>' in html
    assert 'localStorage.setItem("token"' in html
    assert "no-store" in resposta["Cache-Control"]


def test_com_cadastro_valido_vai_direto_para_a_cedula(client, evento, estacao):
    client.cookies[COOKIE_CADASTRO] = valor_do_cookie(evento)
    assert _destino(_entrar(estacao.pk, client=client)) == "/votar"


def test_cadastro_do_ensaio_nao_vale_no_evento(client, estacao):
    client.cookies[COOKIE_CADASTRO] = valor_do_cookie(_ensaio())
    assert _destino(_entrar(estacao.pk, client=client)) == "/visitantes"


def test_rescan_no_mesmo_navegador_devolve_o_mesmo_token(client, estacao, evento):
    primeiro = _emitido(_entrar(estacao.pk, client=client))
    outra = fabricas.estacao(evento, nome="Saída")
    segundo = _emitido(_entrar(outra.pk, client=client))
    assert segundo == primeiro
    assert Token.objects.count() == 1


@pytest.mark.parametrize(
    "valor",
    [
        "abc",
        uuid.uuid4().hex,  # sem hífens
        str(uuid.uuid4()) + "0",  # 37 caracteres
        str(uuid.uuid4()).upper(),
        str(uuid.uuid4()),  # bem formado, mas não existe
        "",
    ],
)
def test_cookie_que_nao_e_token_valido_emite_token_novo(client, estacao, valor):
    client.cookies["token"] = valor
    token = _emitido(_entrar(estacao.pk, client=client))
    assert str(token.pk) != valor


def test_rescan_com_cookie_do_ensaio_emite_token_novo_e_preserva_o_antigo(client, estacao):
    ensaio = _ensaio()
    do_ensaio = fabricas.token(fabricas.estacao(ensaio))
    criado_em = do_ensaio.criado_em
    client.cookies["token"] = str(do_ensaio.pk)
    novo = _emitido(_entrar(estacao.pk, client=client))
    assert novo != do_ensaio and novo.estacao == estacao
    do_ensaio.refresh_from_db()
    assert (do_ensaio.estacao.edicao, do_ensaio.criado_em) == (ensaio, criado_em)


# --- Recusas: a mesma página, sem token ---------------------------------------------

MATRIZ = [
    {"w": "abc", "sig": "0" * 64},
    {"w": "1:", "sig": "0" * 64},
    {"w": ":1700000000", "sig": "0" * 64},
    {"w": "01:1700000000", "sig": "0" * 64},
    {"w": "-1:1700000000", "sig": "0" * 64},
    {"w": "1" * 22 + ":1700000000", "sig": "0" * 64},  # 33 caracteres
    {"w": ["1:1700000000", "1:1700000000"], "sig": "0" * 64},
    {"w": "1:1700000000", "sig": "0" * 63},
    {"w": "1:1700000000", "sig": "0" * 65},
    {"w": "1:1700000000", "sig": "A" * 64},
    {"w": "1:1700000000", "sig": "g" * 64},
    {"w": "1:1700000000"},
    {},
]


@pytest.mark.parametrize("params", MATRIZ)
def test_matriz_de_w_e_sig_da_a_mesma_pagina(client, estacao, corpo_qr_expirado, params):
    resposta = client.get(ROTA, params)
    assert resposta.status_code == 400
    assert resposta.content == corpo_qr_expirado
    assert Token.objects.count() == 0


def test_corpo_identico_ao_do_qr_expirado_de_visitantes(client, corpo_qr_expirado):
    # Sem edição em votação, GET /visitantes devolve a página genérica da F5.
    assert client.get("/visitantes").content == corpo_qr_expirado


@pytest.mark.parametrize("deslocamento, aceito", [(-90, True), (5, True), (-91, False), (6, False)])
def test_janela_de_tolerancia(estacao, corpo_qr_expirado, deslocamento, aceito):
    resposta = _entrar(estacao.pk, ts=AGORA + deslocamento)
    if aceito:
        _emitido(resposta)
    else:
        assert (resposta.status_code, resposta.content) == (400, corpo_qr_expirado)
        assert Token.objects.count() == 0


def test_url_capturada_deixa_de_emitir_apos_a_janela(estacao, relogio, corpo_qr_expirado):
    _emitido(_entrar(estacao.pk))
    relogio.return_value = AGORA + 91
    resposta = _entrar(estacao.pk)
    assert (resposta.status_code, resposta.content) == (400, corpo_qr_expirado)
    assert Token.objects.count() == 1


def _recusa_sem_token(resposta, corpo, antes=0):
    assert resposta.status_code == 400
    assert resposta.content == corpo
    assert "token" not in resposta.cookies
    assert Token.objects.count() == antes


def test_estacao_inexistente_inativa_ou_de_outra_edicao(evento, corpo_qr_expirado):
    inativa = fabricas.estacao(evento, ativa=False)
    do_ensaio = fabricas.estacao(_ensaio())
    for estacao_id in (inativa.pk, do_ensaio.pk, do_ensaio.pk + 1000):
        _recusa_sem_token(_entrar(estacao_id), corpo_qr_expirado)


def test_votacao_encerrada_ou_nunca_aberta_recusa(evento, estacao, corpo_qr_expirado):
    encerrar_votacao(evento.pk)
    _recusa_sem_token(_entrar(estacao.pk), corpo_qr_expirado)
    nunca_aberta = cadastro.edicao(nome="2027/1")
    _recusa_sem_token(_entrar(fabricas.estacao(nunca_aberta).pk), corpo_qr_expirado)


def test_so_get():
    assert Client().post(ROTA).status_code == 405


# --- Rate limit (guardrail 7) --------------------------------------------------------


def test_vinte_por_bloco_da_estacao_e_a_21a_recusa(estacao, corpo_qr_expirado):
    # Clientes sem cookie: cada um é um celular novo. ts diferentes, mesmo bloco de 45 s.
    for i in range(20):
        _emitido(_entrar(estacao.pk, ts=AGORA - (AGORA % 45) + i % 45))
    _recusa_sem_token(_entrar(estacao.pk), corpo_qr_expirado, antes=20)


def test_reescan_tambem_conta(client, estacao, corpo_qr_expirado):
    for _ in range(20):
        _emitido(_entrar(estacao.pk, client=client))
    _recusa_sem_token(_entrar(estacao.pk, client=client), corpo_qr_expirado, antes=1)


def test_bloco_seguinte_tem_contador_proprio(estacao, relogio):
    caches["default"].set(limite.chave_estacao(estacao.pk, AGORA), (20, AGORA + 150), 150)
    proximo = AGORA - (AGORA % 45) + 45
    relogio.return_value = proximo
    _emitido(_entrar(estacao.pk, ts=proximo))


def test_outra_estacao_no_mesmo_bloco_emite(evento, estacao, corpo_qr_expirado):
    caches["default"].set(limite.chave_estacao(estacao.pk, AGORA), (20, AGORA + 150), 150)
    _recusa_sem_token(_entrar(estacao.pk), corpo_qr_expirado)
    outra = fabricas.estacao(evento, nome="Saída")
    _emitido(_entrar(outra.pk))


def test_forjadas_nao_contam(estacao, corpo_qr_expirado):
    forjada = {"w": f"{estacao.pk}:{AGORA}", "sig": "0" * 64}
    for _ in range(50):
        assert Client().get(ROTA, forjada, REMOTE_ADDR=IP_FICTICIO).status_code == 400
    for _ in range(20):
        _emitido(_entrar(estacao.pk))
    _recusa_sem_token(_entrar(estacao.pk), corpo_qr_expirado, antes=20)


def _chave_ip(ip=IP_FICTICIO):
    return "rl:entrar:ip:" + chave_ip(ip)


def test_300_do_mesmo_ip_passam_e_a_301a_recusa(evento, corpo_qr_expirado):
    # Contador pré-carregado (nunca desligado): 299 já contadas.
    caches["default"].set(_chave_ip(), (299, AGORA + 600), 600)
    _emitido(_entrar(fabricas.estacao(evento).pk))
    _recusa_sem_token(_entrar(fabricas.estacao(evento, nome="Saída").pk), corpo_qr_expirado, antes=1)
    # Outro IP, mesma hora: contador próprio.
    _emitido(_entrar(fabricas.estacao(evento, nome="Pátio").pk, ip="198.51.100.9"))


def test_limite_estourado_nao_conta(estacao, corpo_qr_expirado):
    """Recusa pela estação não come o limite do IP que todos dividem."""
    caches["default"].set(limite.chave_estacao(estacao.pk, AGORA), (20, AGORA + 150), 150)
    _recusa_sem_token(_entrar(estacao.pk), corpo_qr_expirado)
    assert caches["default"].get(_chave_ip()) is None


def test_ip_vem_do_cabecalho_configurado(settings, estacao):
    settings.IP_HEADER = "X-Real-Ip"
    _emitido(_entrar(estacao.pk, ip="10.0.0.1", HTTP_X_REAL_IP=IP_FICTICIO))
    assert caches["default"].get(_chave_ip()) == (1, AGORA + 600)
    assert caches["default"].get(_chave_ip("10.0.0.1")) is None


def _linhas_de_cache():
    with connection.cursor() as cursor:
        cursor.execute("SELECT cache_key, value, expires FROM cache_django")
        return cursor.fetchall()


def test_chave_do_ip_e_o_hmac_sem_o_ip_em_claro_e_expira_em_10_min(estacao):
    _emitido(_entrar(estacao.pk))
    linhas = _linhas_de_cache()
    assert linhas and all(IP_FICTICIO not in f"{chave}{valor}" for chave, valor, _ in linhas)
    expira = {chave: expires for chave, _, expires in linhas}
    # O DatabaseCache prefixa a versão (":1:").
    agora = timezone.now()
    assert agora + timedelta(seconds=590) < expira[":1:" + _chave_ip()] <= agora + timedelta(seconds=600)
    chave_estacao = ":1:" + limite.chave_estacao(estacao.pk, AGORA)
    assert agora + timedelta(seconds=140) < expira[chave_estacao] <= agora + timedelta(seconds=150)


def test_nova_emissao_nao_empurra_a_expiracao(evento, relogio):
    """Armadilha A2: o contador do IP zera 10 min após a primeira emissão."""
    _emitido(_entrar(fabricas.estacao(evento).pk))
    primeira = dict((c, e) for c, _, e in _linhas_de_cache())[":1:" + _chave_ip()]
    relogio.return_value = AGORA + 100
    _emitido(_entrar(fabricas.estacao(evento, nome="Saída").pk, ts=AGORA + 100))
    assert caches["default"].get(_chave_ip()) == (2, AGORA + 600)
    segunda = dict((c, e) for c, _, e in _linhas_de_cache())[":1:" + _chave_ip()]
    assert abs((primeira - segunda).total_seconds() - 100) < 5


def test_contador_vencido_recomeca(estacao, relogio):
    caches["default"].set(_chave_ip(), (300, AGORA - 1), 600)
    _emitido(_entrar(estacao.pk))
    assert caches["default"].get(_chave_ip()) == (1, AGORA + 600)


# --- Revisão de código automatizada --------------------------------------------------


def _codigo_do_app():
    app = Path(__file__).resolve().parents[1]
    return [p for p in app.rglob("*.py") if "tests" not in p.parts and "migrations" not in p.parts]


def test_app_nao_le_ip_direto_nem_faz_hmac_de_ip():
    for arquivo in _codigo_do_app():
        texto = arquivo.read_text()
        for proibido in ("REMOTE_ADDR", "X-Forwarded-For", "X_FORWARDED_FOR", "IP_HMAC_SECRET"):
            assert proibido not in texto, f"{proibido} em {arquivo.name}"


def test_entrar_sem_logger():
    for nome in ("views_entrar.py", "limite.py"):
        arvore = ast.parse((Path(__file__).resolve().parents[1] / nome).read_text())
        nomes = {n.id for n in ast.walk(arvore) if isinstance(n, ast.Name)}
        nomes |= {a.name for n in ast.walk(arvore) if isinstance(n, ast.Import | ast.ImportFrom) for a in n.names}
        assert not nomes & {"logging", "logger", "getLogger"}, nome
