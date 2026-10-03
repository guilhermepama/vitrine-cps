"""Critérios de aceite "Segurança" (specs/01-cadastro.md)."""

import os
import subprocess
import sys

import pytest
from django.conf import settings

from cadastro.models import Projeto
from cadastro.seguranca import hash_ra, hash_token, normalizar_ra, ra_confere, token_confere
from cadastro.tests import fabricas


def test_ra_normalizado_ignora_separadores():
    esperado = hash_ra("123456789")
    assert hash_ra("123.456 789") == esperado
    assert hash_ra(" 123-456-789 ") == esperado
    assert hash_ra("123/456/789") == esperado


def test_ra_preserva_zeros_a_esquerda():
    assert normalizar_ra("0012345") == "0012345"
    assert hash_ra("0012345") != hash_ra("12345")


@pytest.mark.parametrize("ra", ["", "   ", "abc", "...", "12a45678", "1234", "1" * 21, "123456789X", "１２３４５"])
def test_ra_invalido_e_recusado(ra):
    with pytest.raises(ValueError):
        hash_ra(ra)
    assert ra_confere(ra, hash_ra("123456")) is False


@pytest.mark.parametrize("ra", ["12345", "1" * 20])
def test_ra_nos_limites_de_tamanho(ra):
    assert normalizar_ra(ra) == ra


def test_hash_do_ra_depende_do_segredo(settings):
    original = hash_ra("123456")
    settings.RA_HMAC_SECRET = "outro-segredo-outro-segredo-1234"
    assert hash_ra("123456") != original


def test_hash_do_ra_nao_contem_o_ra():
    ra = "1234567890123"
    assert ra not in hash_ra(ra)
    assert len(hash_ra(ra)) == 64


def test_ra_confere():
    assert ra_confere("123.456", hash_ra("123456")) is True
    assert ra_confere("123457", hash_ra("123456")) is False


@pytest.mark.parametrize("segredo", ["RA_HMAC_SECRET", "QR_HMAC_SECRET", "IP_HMAC_SECRET"])
def test_aplicacao_nao_sobe_sem_segredo(segredo):
    # Variável vazia (e não ausente): o .env local não a preenche, porque
    # o carregador nunca sobrescreve o que já existe no ambiente.
    ambiente = dict(os.environ, DJANGO_SETTINGS_MODULE="config.settings", **{segredo: ""})
    resultado = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=ambiente, cwd=settings.BASE_DIR, capture_output=True, text=True,
    )
    assert resultado.returncode != 0
    assert segredo in resultado.stderr


@pytest.mark.django_db
def test_regerar_link_invalida_o_anterior_e_nao_grava_o_token():
    p = fabricas.projeto()
    primeiro = p.regerar_link()
    hash_primeiro = p.token_edicao_hash
    assert hash_primeiro == hash_token(primeiro) != primeiro

    segundo = p.regerar_link()
    p.refresh_from_db()
    assert token_confere(segundo, p.token_edicao_hash)
    assert not token_confere(primeiro, p.token_edicao_hash)
    assert p.token_edicao_gerado_em is not None


@pytest.mark.django_db
def test_revogar_link():
    p = fabricas.projeto()
    token = p.regerar_link()
    p.revogar_link()
    p.refresh_from_db()
    assert p.token_edicao_hash is None
    assert not token_confere(token, p.token_edicao_hash)


@pytest.mark.django_db
def test_token_hash_e_unico_mas_varios_nulos_sao_permitidos():
    t = fabricas.turma()
    fabricas.projeto(t, titulo="A")
    fabricas.projeto(t, titulo="B")
    assert Projeto.objects.filter(token_edicao_hash__isnull=True).count() == 2


def test_campos_sensiveis_nao_sao_editaveis():
    campos = {f.name: f for f in Projeto._meta.get_fields() if hasattr(f, "editable")}
    for nome in ["ra_hmac", "token_edicao_hash", "slug", "publicado_em", "reivindicado_em"]:
        assert campos[nome].editable is False, nome
