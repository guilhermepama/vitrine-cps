"""IP do cliente para o rate limit (specs 02 e 03): cabeçalho, normalização e HMAC."""

import hashlib
import hmac

import pytest
from django.test import RequestFactory

from cadastro.seguranca import chave_ip, ip_do_cliente

fabrica = RequestFactory()


def _req(**meta):
    return fabrica.get("/", **meta)


# --- ip_do_cliente ------------------------------------------------------------


def test_sem_cabecalho_configurado_usa_remote_addr(settings):
    settings.IP_HEADER = ""
    req = _req(REMOTE_ADDR="203.0.113.7", HTTP_X_FORWARDED_FOR="198.51.100.1")
    assert ip_do_cliente(req) == "203.0.113.7"


def test_com_cabecalho_configurado_ignora_remote_addr(settings):
    settings.IP_HEADER = "X-Real-IP"
    req = _req(REMOTE_ADDR="10.0.0.1", HTTP_X_REAL_IP="203.0.113.7")
    assert ip_do_cliente(req) == "203.0.113.7"


def test_lista_no_cabecalho_vale_o_ultimo_item(settings):
    """Os primeiros itens do X-Forwarded-For vêm do cliente e podem ser falsos."""
    settings.IP_HEADER = "X-Forwarded-For"
    req = _req(HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8,  203.0.113.7 ")
    assert ip_do_cliente(req) == "203.0.113.7"


def test_ip_falso_mandado_pelo_cliente_nao_muda_a_chave(settings):
    settings.IP_HEADER = "X-Forwarded-For"
    honesto = _req(HTTP_X_FORWARDED_FOR="203.0.113.7")
    forjado = _req(HTTP_X_FORWARDED_FOR="9.9.9.9, 203.0.113.7")
    assert chave_ip(ip_do_cliente(honesto)) == chave_ip(ip_do_cliente(forjado))


def test_cabecalho_configurado_ausente_devolve_vazio(settings):
    settings.IP_HEADER = "X-Forwarded-For"
    assert ip_do_cliente(_req(REMOTE_ADDR="203.0.113.7")) == ""


# --- chave_ip -----------------------------------------------------------------


def _esperado(texto, segredo):
    return hmac.new(segredo.encode(), texto.encode(), hashlib.sha256).hexdigest()


def test_chave_e_hmac_sha256_com_o_segredo_do_ip(settings):
    assert chave_ip("203.0.113.7") == _esperado("203.0.113.7", settings.IP_HMAC_SECRET)


def test_chave_nao_contem_o_ip_em_claro():
    chave = chave_ip("203.0.113.7")
    assert "203.0.113.7" not in chave
    assert len(chave) == 64


def test_chave_muda_com_o_segredo(settings):
    antes = chave_ip("203.0.113.7")
    settings.IP_HMAC_SECRET = "outro-segredo-outro-segredo-1234"
    assert chave_ip("203.0.113.7") != antes


def test_ips_v4_diferentes_tem_chaves_diferentes():
    assert chave_ip("203.0.113.7") != chave_ip("203.0.113.8")


@pytest.mark.parametrize(
    "variante",
    ["2001:db8:abcd:12::1", "2001:0db8:abcd:0012:0000:0000:0000:0001", "2001:DB8:ABCD:12::ffff", " 2001:db8:abcd:12:1:2:3:4 "],
)
def test_ipv6_do_mesmo_64_cai_na_mesma_chave(variante):
    """Mesmo /64 (troca de endereço dentro do bloco do aparelho) e grafias diferentes."""
    assert chave_ip(variante) == chave_ip("2001:db8:abcd:12::1")


def test_ipv6_de_outro_64_tem_outra_chave():
    assert chave_ip("2001:db8:abcd:13::1") != chave_ip("2001:db8:abcd:12::1")


def test_ipv4_mapeado_em_ipv6_e_o_mesmo_ipv4():
    assert chave_ip("::ffff:203.0.113.7") == chave_ip("203.0.113.7")


@pytest.mark.parametrize("invalido", ["", None, "abc", "999.1.1.1", "203.0.113.7:8080", "1.2.3.4, 5.6.7.8"])
def test_ip_invalido_ou_ausente_cai_na_mesma_chave_fixa(invalido):
    assert chave_ip(invalido) == chave_ip("lixo")
    assert chave_ip(invalido) != chave_ip("203.0.113.7")
