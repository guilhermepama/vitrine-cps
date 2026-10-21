"""Migration 0004: voto com três notas (ADR-012, resposta P-B no PR #85).

Só aplica com `votos` vazia: voto antigo não tem nota, e nota não se inventa.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from cadastro.tests import fabricas as cadastro

ANTES = [("votacao", "0003_permissao_operar_estacao")]
DEPOIS = [("votacao", "0004_voto_tres_notas")]

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def voltar_ao_fim():
    yield
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM votos")  # a 0004 recusaria o voto que o teste deixou
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


def _migrar(alvo):
    executor = MigrationExecutor(connection)
    executor.migrate(alvo)
    return executor.loader.project_state(alvo).apps


def test_aplica_com_votos_vazia(voltar_ao_fim):
    _migrar(ANTES)
    apps = _migrar(DEPOIS)
    assert {"impacto_social", "inovacao", "impacto_ambiental"} <= {f.name for f in apps.get_model("votacao", "Voto")._meta.fields}


def test_com_voto_existente_falha_com_mensagem_e_nao_grava_nota(voltar_ao_fim):
    apps = _migrar(ANTES)
    Estacao, Token, Voto = (apps.get_model("votacao", n) for n in ("Estacao", "Token", "Voto"))
    # O cadastro não muda nesta migration: a fábrica atual monta os pais.
    projeto = cadastro.projeto()
    edicao = projeto.turma.edicao
    estacao = Estacao.objects.create(edicao_id=edicao.pk, nome="Entrada")
    token = Token.objects.create(estacao=estacao)
    Voto.objects.create(token=token, projeto_id=projeto.pk)

    with pytest.raises(RuntimeError, match="votos existentes sem notas"):
        _migrar(DEPOIS)

    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM votos")
        assert cursor.fetchone()[0] == 1
        colunas = {c.name for c in connection.introspection.get_table_description(cursor, "votos")}
    assert "impacto_social" not in colunas
