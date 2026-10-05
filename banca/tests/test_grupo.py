"""Grupo `digitacao-banca` e revisão de código (spec 06)."""

import re
from pathlib import Path

import pytest
from django.apps import apps
from django.contrib.auth.models import Group, Permission

from banca.sinais import GRUPO_DIGITACAO, criar_grupo_digitacao

pytestmark = pytest.mark.django_db

ESPERADAS = {
    "add_avaliacao",
    "change_avaliacao",
    "view_avaliacao",
    "add_nota",
    "change_nota",
    "view_nota",
    "view_jurado",
    "view_criterio",
}


def _codenames():
    grupo = Group.objects.get(name=GRUPO_DIGITACAO)
    return {(p.content_type.app_label, p.codename) for p in grupo.permissions.select_related("content_type")}


def test_grupo_existe_depois_do_migrate_com_exatamente_as_permissoes():
    assert _codenames() == {("banca", c) for c in ESPERADAS}


def test_rodar_de_novo_nao_muda_o_grupo():
    grupo = Group.objects.get(name=GRUPO_DIGITACAO)
    grupo.permissions.add(Permission.objects.get(codename="delete_avaliacao"))
    criar_grupo_digitacao(sender=apps.get_app_config("banca"))
    criar_grupo_digitacao(sender=apps.get_app_config("banca"))
    assert Group.objects.filter(name=GRUPO_DIGITACAO).count() == 1
    assert _codenames() == {("banca", c) for c in ESPERADAS}


def test_migrate_parcial_sem_a_banca_nao_quebra():
    """`migrate auth` num banco novo: o estado das migrations ainda não tem a banca."""

    class EstadoSemBanca:
        def get_model(self, app, model):
            raise LookupError

    Group.objects.filter(name=GRUPO_DIGITACAO).delete()
    criar_grupo_digitacao(sender=apps.get_app_config("banca"), apps=EstadoSemBanca(), using="default")
    assert not Group.objects.filter(name=GRUPO_DIGITACAO).exists()


def test_permissoes_proprias_existem():
    assert Permission.objects.filter(content_type__app_label="banca", codename="imprimir_ficha").exists()
    assert Permission.objects.filter(content_type__app_label="banca", codename="concluir_conferencia").exists()


def test_sem_update_nem_operacoes_em_lote_no_app():
    """Regra do PR #17: mudanças só por save()/delete() dos objetos."""
    raiz = Path(__file__).resolve().parents[1]
    proibido = re.compile(r"\.(update|bulk_update|bulk_create)\(|\)\s*\.\s*delete\(|objects\.[^\n]*\.delete\(")
    for arquivo in raiz.rglob("*.py"):
        if "tests" in arquivo.parts or "migrations" in arquivo.parts:
            continue
        assert not proibido.search(arquivo.read_text()), arquivo
