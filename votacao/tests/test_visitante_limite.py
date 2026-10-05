"""Rate limit do POST /visitantes — fatia F5b (decisão 4 do PR #33,
specs/03-credenciamento-votacao.md, "Cadastro do visitante").

Critério de aceite fechado aqui: "(F5b) 300 envios de `POST /visitantes`
do mesmo IP em 10 min passam; o 301º → 400 com o formulário e a mensagem
genérica, nada gravado, sem travar a `Edicao`; a chave no cache é a de
`chave_ip`, sem o IP em claro".

Os testes pré-carregam o contador; nunca desligam o limite (G7).
"""

import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest import mock

import pytest
from django.core.cache import caches
from django.core.management import call_command
from django.db import connection
from django.test import Client, RequestFactory
from django.utils import timezone

from cadastro.seguranca import chave_ip
from cadastro.tests import fabricas as cadastro
from votacao import limite, views_visitante
from votacao.models import Visitante
from votacao.servicos import abrir_votacao, edicao_em_votacao, encerrar_votacao

pytestmark = pytest.mark.django_db

ROTA = "/visitantes"
AGORA = 1_793_000_000
IP_FICTICIO = "203.0.113.7"
# Bloco fixo de 10 min (decisão do coordenador no PR #35): o contador expira
# no fim do bloco em que AGORA cai, não em AGORA + 600.
FIM_BLOCO = AGORA - AGORA % 600 + 600
MENSAGEM = "Não foi possível concluir o cadastro. Confira os campos."
DADOS = {"nome": "Ana Souza", "email": "ana@example.com", "telefone": "(17) 99999-9999", "consentimento": "on"}


@pytest.fixture(autouse=True)
def relogio():
    with mock.patch("votacao.assinatura.agora", return_value=AGORA) as fixo:
        yield fixo


@pytest.fixture(autouse=True)
def evento():
    call_command("createcachetable", verbosity=0)
    caches["default"].clear()
    edicao = cadastro.edicao()
    assert abrir_votacao(edicao.pk) is None
    return edicao


def _celular(ip=IP_FICTICIO):
    return Client(REMOTE_ADDR=ip)


def _chave(ip=IP_FICTICIO, momento=AGORA):
    return f"rl:visitantes:ip:{chave_ip(ip)}:{momento // 600}"


def _contador(ip=IP_FICTICIO):
    return caches["default"].get(_chave(ip))


def _pre_carregar(contagem, ip=IP_FICTICIO):
    caches["default"].set(_chave(ip), (contagem, FIM_BLOCO), FIM_BLOCO - AGORA)


def _sem_csrf(resposta):
    return re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', "", resposta.content.decode())


def test_a_300a_passa_e_a_301a_recusa(evento):
    _pre_carregar(299)
    resposta = _celular().post(ROTA, DADOS)
    assert resposta.status_code == 302
    assert Visitante.objects.count() == 1
    assert _contador() == (300, FIM_BLOCO)

    recusa = _celular().post(ROTA, DADOS)
    assert recusa.status_code == 400
    assert MENSAGEM in recusa.content.decode()
    assert "cadastro" not in recusa.cookies
    assert Visitante.objects.count() == 1
    assert _contador() == (300, FIM_BLOCO)  # recusa não conta


def test_recusa_pelo_limite_nao_trava_a_edicao(evento):
    _pre_carregar(300)
    with mock.patch.object(views_visitante, "edicao_em_votacao", wraps=edicao_em_votacao) as trava:
        assert _celular().post(ROTA, DADOS).status_code == 400
    trava.assert_not_called()
    assert Visitante.objects.count() == 0


def test_recusa_dentro_da_trava_quando_o_teto_chega_depois_da_pre_checagem(evento):
    """Outro envio completou o teto entre a leitura sem trava e a trava: a
    contagem de dentro recusa, com a mesma resposta, nada gravado."""
    _pre_carregar(300)
    with mock.patch.object(views_visitante, "cadastro_no_teto", return_value=False):
        recusa = _celular().post(ROTA, DADOS)
    assert recusa.status_code == 400
    assert MENSAGEM in recusa.content.decode()
    assert Visitante.objects.count() == 0
    assert _contador() == (300, FIM_BLOCO)


def test_sem_edicao_em_votacao_nao_gasta_vaga(evento):
    encerrar_votacao(evento.pk)
    assert _celular().post(ROTA, DADOS).status_code == 400  # "QR expirado"
    assert _contador() is None


def test_corpo_da_recusa_e_o_do_formulario_invalido(evento):
    """Nada revela que foi o limite: mesmo formulário, mesma mensagem, mesmos
    campos de volta (o consentimento volta desmarcado nos dois)."""
    invalido = _celular().post(ROTA, {**DADOS, "consentimento": ""})
    _pre_carregar(300)
    recusa = _celular().post(ROTA, DADOS)
    assert (recusa.status_code, invalido.status_code) == (400, 400)
    assert _sem_csrf(recusa) == _sem_csrf(invalido)


def test_formulario_invalido_nao_consulta_o_banco_nem_conta(evento, django_assert_num_queries):
    """G12: a validação vem antes do contador, que mora no banco (DatabaseCache)."""
    _pre_carregar(300)
    with django_assert_num_queries(0):
        assert _celular().post(ROTA, {**DADOS, "nome": "A"}).status_code == 400
    assert _contador() == (300, FIM_BLOCO)


def test_outro_ip_tem_contador_proprio(evento):
    _pre_carregar(300)
    assert _celular("198.51.100.9").post(ROTA, DADOS).status_code == 302


def test_contador_proprio_separado_do_entrar(evento):
    """Mesmo teto, contadores diferentes: o IP do Wi-Fi não paga duas vagas por visitante."""
    caches["default"].set(limite.chave_do_ip(_request()), (300, AGORA + 600), 600)
    assert _celular().post(ROTA, DADOS).status_code == 302
    assert caches["default"].get(limite.chave_do_ip(_request())) == (300, AGORA + 600)
    assert _contador() == (1, FIM_BLOCO)


def _request():
    return RequestFactory(REMOTE_ADDR=IP_FICTICIO).post(ROTA)


def _linhas():
    with connection.cursor() as cursor:
        cursor.execute("SELECT cache_key, value, expires FROM cache_django")
        return cursor.fetchall()


def test_chave_e_o_hmac_do_ip_com_o_bloco_sem_o_ip_em_claro(evento):
    assert _celular().post(ROTA, DADOS).status_code == 302
    linhas = _linhas()
    esperada = f"rl:visitantes:ip:{chave_ip(IP_FICTICIO)}:{AGORA // 600}"
    assert [chave for chave, _, _ in linhas] == [":1:" + esperada]
    assert all(IP_FICTICIO not in f"{chave}{valor}" for chave, valor, _ in linhas)
    # Expira no fim do bloco (AGORA + 400 aqui), não em AGORA + 600.
    agora = timezone.now()
    restante = FIM_BLOCO - AGORA
    assert agora + timedelta(seconds=restante - 10) < linhas[0][2] <= agora + timedelta(seconds=restante)


def test_expiracao_nao_guarda_o_horario_do_cadastro(evento, relogio):
    """Correlação pelo horário (B1, decisão do coordenador no PR #35): dois
    IPs que se cadastram em segundos diferentes do mesmo bloco ficam com o
    mesmo `expira_em`, e a chave não leva o segundo do cadastro."""
    assert _celular().post(ROTA, DADOS).status_code == 302
    relogio.return_value = AGORA + 137
    assert _celular("198.51.100.9").post(ROTA, {**DADOS, "email": "bia@example.com"}).status_code == 302
    valores = {caches["default"].get(_chave(ip, AGORA + 137)) for ip in (IP_FICTICIO, "198.51.100.9")}
    assert valores == {(1, FIM_BLOCO)}


def test_novo_cadastro_nao_empurra_a_expiracao(evento, relogio):
    """Armadilha A2 no contador do cadastro: o segundo envio no mesmo bloco
    mantém o fim do bloco."""
    assert _celular().post(ROTA, DADOS).status_code == 302
    relogio.return_value = AGORA + 100
    assert _celular().post(ROTA, {**DADOS, "email": "bia@example.com"}).status_code == 302
    assert caches["default"].get(_chave(momento=AGORA + 100)) == (2, FIM_BLOCO)


def test_bloco_seguinte_tem_contador_proprio(evento, relogio):
    """Na virada do bloco o contador recomeça (aceito: até 2× o teto na
    virada, como a janela fixa do /entrar)."""
    _pre_carregar(300)
    assert _celular().post(ROTA, DADOS).status_code == 400
    relogio.return_value = FIM_BLOCO
    assert _celular().post(ROTA, DADOS).status_code == 302
    assert caches["default"].get(_chave(momento=FIM_BLOCO)) == (1, FIM_BLOCO + 600)


def test_ip_vem_do_cabecalho_configurado(settings, evento):
    settings.IP_HEADER = "X-Real-Ip"
    assert Client(REMOTE_ADDR="10.0.0.1").post(ROTA, DADOS, HTTP_X_REAL_IP=IP_FICTICIO).status_code == 302
    assert _contador() == (1, FIM_BLOCO)
    assert _contador("10.0.0.1") is None


def test_cadastro_ja_valido_tambem_conta(evento):
    """A contagem vem logo depois da trava, antes de conferir o cadastro:
    quem reenvia com cadastro válido gasta uma vaga."""
    celular = _celular()
    assert celular.post(ROTA, DADOS).status_code == 302
    assert celular.post(ROTA, DADOS).status_code == 302
    assert Visitante.objects.count() == 1
    assert _contador() == (2, FIM_BLOCO)


@pytest.mark.django_db(transaction=True)
def test_rajada_simultanea_nunca_passa_do_teto(evento):
    """Contador em 295 e 12 envios simultâneos do mesmo IP: exatamente 5
    passam. A contagem que vale é a de dentro da trava da Edicao."""
    _pre_carregar(295)
    n = 12
    barreira = threading.Barrier(n)

    def enviar(_):
        try:
            barreira.wait(timeout=10)
            return _celular().post(ROTA, DADOS).status_code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=n) as executor:
        status = list(executor.map(enviar, range(n)))
    assert (status.count(302), status.count(400)) == (5, n - 5)
    assert Visitante.objects.count() == 5
    assert _contador() == (300, FIM_BLOCO)
