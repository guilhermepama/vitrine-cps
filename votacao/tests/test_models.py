"""Schema da votação — fatia F1 (specs/03-credenciamento-votacao.md).

Critérios de aceite fechados aqui (citados em cada teste):
- Estação: "Mudar a edição de estação com token emitido → ValidationError,
  edição inalterada; sem token emitido → permitido" e "Apagar estação com
  token emitido → bloqueado (ProtectedError)".
- Visitante: "não tem nenhuma coluna ligando ao token, voto ou estação" e
  "não tem outro campo de data/hora além de consentimento_em".
- B1: "id é UUID com default=uuid4; a migration não cria sequência" e "dois
  cadastros seguidos geram ids sem relação de ordem" (nível do model).
- Base do guardrail 4: unicidade (token, projeto) no banco (o 409 é da F6).
"""

import uuid
from datetime import UTC, datetime

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, models, transaction
from django.db.models import ProtectedError

from cadastro.tests import fabricas as cadastro
from votacao.models import Estacao, Token, Visitante, Voto
from votacao.tests import fabricas
from votacao.tests.fabricas import BRASILIA

pytestmark = pytest.mark.django_db


# --- Voto: unicidade no banco (guardrail 4) ----------------------------------


def test_segundo_voto_do_mesmo_token_no_mesmo_projeto_e_recusado_pelo_banco():
    v = fabricas.voto()
    with pytest.raises(IntegrityError), transaction.atomic():
        Voto.objects.create(token=v.token, projeto=v.projeto)
    assert Voto.objects.count() == 1


def test_unicidade_vale_tambem_para_bulk_create():
    """A regra não depende do save(): o banco barra qualquer caminho."""
    v = fabricas.voto()
    with pytest.raises(IntegrityError), transaction.atomic():
        Voto.objects.bulk_create([Voto(token=v.token, projeto=v.projeto)])


def test_mesmo_token_vota_em_projetos_diferentes():
    v = fabricas.voto()
    outro = cadastro.projeto(turma_=v.projeto.turma, titulo="Horta Comunitária")
    Voto.objects.create(token=v.token, projeto=outro)
    assert v.token.votos.count() == 2


def test_tokens_diferentes_votam_no_mesmo_projeto():
    v = fabricas.voto()
    Voto.objects.create(token=fabricas.token(v.token.estacao), projeto=v.projeto)
    assert v.projeto.votos.count() == 2


def test_constraint_de_unicidade_existe_no_banco():
    with connection.cursor() as cursor:
        restricoes = connection.introspection.get_constraints(cursor, Voto._meta.db_table)
    unica = restricoes["voto_unico_por_token_projeto"]
    assert unica["unique"] and unica["columns"] == ["token_id", "projeto_id"]


# --- PROTECT: nada do ensaio ou do evento some em cascata ---------------------


def test_apagar_estacao_com_token_e_bloqueado():
    """Aceite: "Apagar estação com token emitido → bloqueado (ProtectedError)"."""
    t = fabricas.token()
    with pytest.raises(ProtectedError):
        t.estacao.delete()
    assert Estacao.objects.filter(pk=t.estacao_id).exists()


def test_apagar_estacao_sem_token_e_permitido():
    e = fabricas.estacao()
    e.delete()
    assert not Estacao.objects.exists()


def test_apagar_token_com_voto_e_bloqueado():
    v = fabricas.voto()
    with pytest.raises(ProtectedError):
        v.token.delete()


def test_apagar_projeto_com_voto_e_bloqueado():
    v = fabricas.voto()
    with pytest.raises(ProtectedError):
        v.projeto.delete()


def test_apagar_edicao_com_estacao_e_bloqueado():
    e = fabricas.estacao()
    with pytest.raises(ProtectedError):
        e.edicao.delete()


def test_apagar_edicao_com_visitante_e_bloqueado():
    v = fabricas.visitante()
    with pytest.raises(ProtectedError):
        v.edicao.delete()


@pytest.mark.parametrize(
    "model,campo",
    [(Estacao, "edicao"), (Token, "estacao"), (Voto, "token"), (Voto, "projeto"), (Visitante, "edicao")],
)
def test_chaves_estrangeiras_sao_protect(model, campo):
    assert model._meta.get_field(campo).remote_field.on_delete is models.PROTECT


# --- Estação: a edição não muda depois da primeira emissão --------------------


def test_estacao_com_token_nao_muda_de_edicao_no_save():
    """Aceite: "Mudar a edição de estação com token emitido → ValidationError, edição inalterada"."""
    t = fabricas.token()
    estacao = t.estacao
    original = estacao.edicao_id
    estacao.edicao = cadastro.edicao(nome="Ensaio 2026/2")
    with pytest.raises(ValidationError):
        estacao.save()
    assert Estacao.objects.get(pk=estacao.pk).edicao_id == original


def test_estacao_com_token_nao_muda_de_edicao_no_full_clean():
    """O admin (F2) chama full_clean(): o erro aparece no campo edição."""
    estacao = fabricas.token().estacao
    estacao.edicao = cadastro.edicao(nome="Ensaio 2026/2")
    with pytest.raises(ValidationError) as erro:
        estacao.full_clean()
    assert "edicao" in erro.value.message_dict


def test_estacao_sem_token_muda_de_edicao():
    """Aceite: "sem token emitido → permitido"."""
    estacao = fabricas.estacao()
    ensaio = cadastro.edicao(nome="Ensaio 2026/2")
    estacao.edicao = ensaio
    estacao.full_clean()
    estacao.save()
    assert Estacao.objects.get(pk=estacao.pk).edicao_id == ensaio.pk


def test_estacao_com_token_ainda_muda_nome_e_desativa():
    """Para tirar de uso, desativa-se (spec 03, "Estação")."""
    estacao = fabricas.token().estacao
    estacao.nome = "Saída"
    estacao.ativa = False
    estacao.full_clean()
    estacao.save()
    estacao.refresh_from_db()
    assert (estacao.nome, estacao.ativa) == ("Saída", False)


def test_estacao_nasce_ativa():
    assert fabricas.estacao().ativa is True


# --- Token ---------------------------------------------------------------------


def test_token_e_uuid4_gerado_no_servidor():
    campo = Token._meta.get_field("id")
    assert campo.primary_key and not campo.editable and campo.default is uuid.uuid4
    assert fabricas.token().id.version == 4


def test_token_nao_tem_coluna_de_edicao():
    """A edição do token é a da estação que o emitiu."""
    with connection.cursor() as cursor:
        descricao = connection.introspection.get_table_description(cursor, Token._meta.db_table)
    assert {c.name for c in descricao} == {"id", "estacao_id", "criado_em"}


# --- Visitante: sem vínculo com token ou voto (guardrail 6, ADR-003) ----------

# Lista de colunas permitidas, não busca por nome proibido (armadilha A1 do plano).
COLUNAS_PERMITIDAS = {"id", "nome", "email", "telefone", "consentimento_em", "edicao_id"}


def _colunas(tabela):
    with connection.cursor() as cursor:
        return {c.name: c for c in connection.introspection.get_table_description(cursor, tabela)}


def test_tabela_de_cadastro_tem_so_as_colunas_permitidas():
    """Aceite: "visitantes não tem nenhuma coluna ligando ao token, voto ou estação"."""
    assert Visitante._meta.db_table == "visitantes"
    assert set(_colunas("visitantes")) == COLUNAS_PERMITIDAS


def test_unica_chave_estrangeira_do_cadastro_e_a_edicao():
    with connection.cursor() as cursor:
        restricoes = connection.introspection.get_constraints(cursor, "visitantes")
    estrangeiras = {r["foreign_key"] for r in restricoes.values() if r["foreign_key"]}
    assert estrangeiras == {("cadastro_edicao", "id")}


def test_unico_campo_de_data_hora_e_o_consentimento_sem_auto_now():
    """Aceite: "não tem outro campo de data/hora além de consentimento_em (sem auto_now/auto_now_add)"."""
    datas = [f for f in Visitante._meta.get_fields() if isinstance(f, (models.DateField, models.TimeField))]
    assert [f.name for f in datas] == ["consentimento_em"]
    assert not datas[0].auto_now and not datas[0].auto_now_add
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s AND (data_type LIKE %s OR data_type LIKE %s OR data_type = %s)",
            ["visitantes", "timestamp%", "time %", "date"],
        )
        tipos_de_data = {linha[0] for linha in cursor.fetchall()}
    assert tipos_de_data == {"consentimento_em"}


def test_id_do_cadastro_e_uuid4_sem_sequencia():
    """Aceite B1: "visitantes.id é UUID com default=uuid4; a migration não cria sequência"."""
    campo = Visitante._meta.get_field("id")
    assert isinstance(campo, models.UUIDField) and campo.default is uuid.uuid4 and not campo.editable
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_get_serial_sequence(%s, %s)", ["visitantes", "id"])
        assert cursor.fetchone()[0] is None
        cursor.execute(
            "SELECT count(*) FROM pg_depend d JOIN pg_class s ON s.oid = d.objid "
            "WHERE s.relkind = 'S' AND d.refobjid = %s::regclass",
            ["visitantes"],
        )
        assert cursor.fetchone()[0] == 0


def test_ids_de_cadastros_seguidos_nao_tem_ordem():
    """Aceite B1: "dois cadastros seguidos geram ids sem relação de ordem (não é inteiro; não é UUID v1/v7)"."""
    edicao = cadastro.edicao()
    ids = [fabricas.visitante(edicao, email=f"v{n}@example.com").id for n in range(20)]
    assert all(isinstance(i, uuid.UUID) and i.version == 4 for i in ids)
    assert len(set(ids)) == 20
    assert sorted(ids) != ids  # 20 uuid4 em ordem crescente por acaso: 1 em 20!


def test_cadastro_nao_tem_ordenacao_padrao():
    assert Visitante._meta.ordering == []


# --- Visitante: consentimento truncado para a hora -----------------------------


def test_consentimento_e_gravado_truncado_para_a_hora():
    """Exemplo da spec 03: 19:42:17 de 25/10/2026 em Brasília → 22:00:00 UTC."""
    aceite = datetime(2026, 10, 25, 19, 42, 17, 123456, tzinfo=BRASILIA)
    v = fabricas.visitante(consentimento_em=aceite)
    v.refresh_from_db()
    assert v.consentimento_em == datetime(2026, 10, 25, 22, 0, tzinfo=UTC)
    assert v.consentimento_em.astimezone(BRASILIA).hour == 19


@pytest.mark.parametrize("minuto,segundo,micro", [(42, 0, 0), (0, 17, 0), (0, 0, 1)])
def test_banco_recusa_consentimento_fora_da_hora_cheia(minuto, segundo, micro):
    """bulk_create pula o save(): a constraint do banco segura o truncamento."""
    aceite = datetime(2026, 10, 25, 19, minuto, segundo, micro, tzinfo=BRASILIA)
    edicao = cadastro.edicao()
    with pytest.raises(IntegrityError), transaction.atomic():
        Visitante.objects.bulk_create(
            [Visitante(nome="Visitante", email="v@example.com", consentimento_em=aceite, edicao=edicao)]
        )


# --- Visitante: telefone só com dígitos ----------------------------------------


@pytest.mark.parametrize("telefone", [None, "17999999999", "5517999999999"])
def test_telefone_vazio_ou_so_digitos_e_aceito(telefone):
    v = fabricas.visitante(telefone=telefone)
    v.refresh_from_db()
    assert v.telefone == telefone


@pytest.mark.parametrize("telefone", ["(17) 999999", "+5517999999", "179999999", ""])
def test_banco_recusa_telefone_que_nao_e_so_digitos(telefone):
    with pytest.raises(IntegrityError), transaction.atomic():
        fabricas.visitante(telefone=telefone)
