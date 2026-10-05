"""Digitação das fichas no admin, em dois passos (spec 06, fatia 3)."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from banca.admin import CONFERENCIA_DESFEITA
from banca.models import Avaliacao, Criterio, Nota
from banca.sinais import GRUPO_DIGITACAO
from banca.tests import fabricas
from cadastro.models import Projeto
from cadastro.tests import fabricas as cadastro

pytestmark = pytest.mark.django_db
User = get_user_model()
ADD = reverse("admin:banca_avaliacao_add")
MENSAGEM_DUPLICATA = "Esta ficha já foi digitada; edite a existente."
FORMATO = "no máximo uma casa decimal"
LINHAS = "não conferem com as notas gravadas"


@pytest.fixture
def superusuario():
    return User.objects.create_superuser("coord", "coord@example.com", "senha-forte-123")


@pytest.fixture
def admin_client(client, superusuario):
    client.force_login(superusuario)
    return client


@pytest.fixture
def barbara():
    usuario = User.objects.create_user("barbara", "b@example.com", "senha-forte-123", is_staff=True)
    usuario.groups.add(Group.objects.get(name=GRUPO_DIGITACAO))
    return usuario


@pytest.fixture
def digitacao(client, barbara):
    client.force_login(barbara)
    return client


@pytest.fixture
def ficha():
    """Edição aberta com 3 critérios, um jurado na turma com 2 projetos publicados."""
    edicao, turma, projetos = fabricas.cenario(criterios=3)
    return edicao, fabricas.jurado(edicao, turma), projetos


def _criterios(edicao):
    return list(Criterio.objects.filter(edicao=edicao).order_by("ordem"))


def _post(projeto, criterios, valores, inicial=0, ids=None, **extra):
    dados = {
        "projeto": projeto.pk,
        "notas-TOTAL_FORMS": len(criterios),
        "notas-INITIAL_FORMS": inicial,
        "notas-MIN_NUM_FORMS": 0,
        "notas-MAX_NUM_FORMS": 1000,
        **extra,
    }
    for i, (criterio, valor) in enumerate(zip(criterios, valores, strict=True)):
        dados[f"notas-{i}-criterio"] = criterio.pk
        dados[f"notas-{i}-valor"] = valor
        if ids:
            dados[f"notas-{i}-id"] = ids[i]
    return dados


def _passo2(jurado):
    return f"{ADD}?jurado={jurado.pk}"


def _nada_gravado():
    return not Avaliacao.objects.exists() and not Nota.objects.exists()


# --- Passo 1 e passo 2 ----------------------------------------------------------------------


def test_passo1_lista_so_jurados_de_edicoes_com_votacao_aberta(digitacao, ficha):
    edicao, jurado, _ = ficha
    ensaio = cadastro.edicao(nome="Ensaio 2026/2")
    fechado = fabricas.jurado(ensaio, cadastro.turma(ensaio, cadastro.curso("GTUR")), nome="Bruno")
    resposta = digitacao.get(ADD)
    corpo = resposta.content.decode()
    assert resposta.status_code == 200
    assert f'value="{jurado.pk}"' in corpo and f"{edicao} · Ana" in corpo
    assert f'value="{fechado.pk}"' not in corpo
    assert 'name="projeto"' not in corpo and "notas-TOTAL_FORMS" not in corpo


def test_passo1_redireciona_para_o_passo2(digitacao, ficha):
    jurado = ficha[1]
    resposta = digitacao.post(ADD, {"jurado": jurado.pk})
    assert resposta.status_code == 302 and resposta["Location"] == _passo2(jurado)
    assert _nada_gravado()


def test_passo1_nao_grava_nem_com_post_completo(digitacao, ficha):
    edicao, jurado, projetos = ficha
    dados = _post(projetos[0], _criterios(edicao), ["7"] * 3, jurado=jurado.pk)
    assert digitacao.post(ADD, dados).status_code == 302
    assert _nada_gravado()


def test_passo2_lista_so_publicados_das_turmas_do_jurado(digitacao, ficha):
    edicao, jurado, projetos = ficha
    turma = projetos[0].turma
    rascunho = cadastro.projeto(turma, titulo="Rascunho", status=Projeto.Status.EM_REVISAO)
    gtur = cadastro.turma(edicao, cadastro.curso("GTUR"))
    outra_turma = cadastro.projeto(gtur, titulo="Outra", status=fabricas.PUBLICADO)
    corpo = digitacao.get(_passo2(jurado)).content.decode()
    assert f"#{projetos[0].pk} — Projeto 0 ({turma.rotulo})" in corpo
    assert f'<option value="{rascunho.pk}"' not in corpo and f'<option value="{outra_turma.pk}"' not in corpo
    assert f'<option value="{projetos[1].pk}"' in corpo
    assert 'name="notas-TOTAL_FORMS" value="3"' in corpo and 'name="notas-2-valor"' in corpo
    assert 'name="notas-3-valor"' not in corpo
    for criterio in _criterios(edicao):
        assert criterio.nome in corpo


@pytest.mark.parametrize("valor", ["999999", "abc", "-1", "", "²", "99999999999999999999"])
def test_jurado_invalido_volta_ao_passo1(digitacao, ficha, valor):
    resposta = digitacao.get(f"{ADD}?jurado={valor}")
    assert resposta.status_code == 302 and resposta["Location"] == ADD


def test_edicao_sem_votacao_aberta_volta_ao_passo1_e_nao_grava(digitacao):
    edicao = cadastro.edicao(nome="Ensaio 2026/2")
    turma = cadastro.turma(edicao, cadastro.curso("GTUR"))
    projeto = cadastro.projeto(turma, status=fabricas.PUBLICADO)
    criterio = Criterio.objects.create(edicao=edicao, nome="C", ordem=1)
    jurado = fabricas.jurado(edicao, turma)
    assert digitacao.get(_passo2(jurado))["Location"] == ADD
    resposta = digitacao.post(_passo2(jurado), _post(projeto, [criterio], ["7"]))
    assert resposta.status_code == 302 and resposta["Location"] == ADD
    assert _nada_gravado()


# --- Gravar -------------------------------------------------------------------------------------


def test_todos_os_criterios_gravam_avaliacao_e_notas(digitacao, barbara, ficha):
    edicao, jurado, projetos = ficha
    resposta = digitacao.post(_passo2(jurado), _post(projetos[0], _criterios(edicao), ["7,5", "8", "10"]))
    assert resposta.status_code == 302
    avaliacao = Avaliacao.objects.get()
    assert (avaliacao.jurado, avaliacao.projeto, avaliacao.digitado_por) == (jurado, projetos[0], barbara)
    assert avaliacao.digitado_em is not None and avaliacao.alterado_por is None and avaliacao.alterado_em is None
    notas = list(avaliacao.notas.order_by("criterio__ordem").values_list("valor", flat=True))
    assert notas == [Decimal("7.5"), Decimal("8"), Decimal("10")]


def test_post_nao_troca_o_jurado_fixo(digitacao, ficha):
    edicao, jurado, projetos = ficha
    outro = fabricas.jurado(edicao, projetos[0].turma, nome="Bia")
    dados = _post(projetos[0], _criterios(edicao), ["7"] * 3, jurado=outro.pk)
    assert digitacao.post(_passo2(jurado), dados).status_code == 302
    assert Avaliacao.objects.get().jurado == jurado


def test_salvar_e_adicionar_outra_mantem_o_jurado(digitacao, ficha):
    """O admin do Django 5.2 já preserva a query string do "Adicionar"."""
    edicao, jurado, projetos = ficha
    dados = _post(projetos[0], _criterios(edicao), ["7"] * 3, _addanother="1")
    resposta = digitacao.post(_passo2(jurado), dados)
    assert resposta.status_code == 302 and resposta["Location"] == _passo2(jurado)


def _recusado(resposta, *textos):
    corpo = resposta.content.decode()
    assert resposta.status_code == 200, resposta.status_code
    for texto in textos:
        assert texto in corpo, texto
    assert _nada_gravado()


def test_criterio_em_branco_e_recusado(digitacao, ficha):
    edicao, jurado, projetos = ficha
    _recusado(digitacao.post(_passo2(jurado), _post(projetos[0], _criterios(edicao), ["7", "", "8"])))


@pytest.mark.parametrize(
    "valor, erro",
    [
        ("7,55", FORMATO),
        ("11", "menor ou igual a 10"),
        ("10,1", "menor ou igual a 10"),
        ("99", "menor ou igual a 10"),
        ("-1", FORMATO),
        ("abc", FORMATO),
        ("1e1", FORMATO),
        ("1E-1", FORMATO),
        ("1_0", FORMATO),
        ("７,５", FORMATO),
        ("7,", FORMATO),
        (",5", FORMATO),
        ("7 ,5", FORMATO),
        ("NaN", FORMATO),
    ],
)
def test_nota_invalida_e_recusada(digitacao, ficha, valor, erro):
    edicao, jurado, projetos = ficha
    _recusado(digitacao.post(_passo2(jurado), _post(projetos[0], _criterios(edicao), [valor, "7", "8"])), erro)


def test_criterio_a_menos_e_recusado(digitacao, ficha):
    edicao, jurado, projetos = ficha
    resposta = digitacao.post(_passo2(jurado), _post(projetos[0], _criterios(edicao)[:2], ["7", "8"]))
    _recusado(resposta, "envie ao menos 3 formulários")


def test_criterio_a_mais_e_recusado(digitacao, ficha):
    edicao, jurado, projetos = ficha
    criterios = _criterios(edicao)
    resposta = digitacao.post(_passo2(jurado), _post(projetos[0], criterios + criterios[:1], ["7", "8", "9", "6"]))
    _recusado(resposta, "envie no máximo 3 formulários")


def test_criterio_repetido_no_lugar_de_outro_e_recusado(digitacao, ficha):
    edicao, jurado, projetos = ficha
    a, b, _ = _criterios(edicao)
    _recusado(digitacao.post(_passo2(jurado), _post(projetos[0], [a, b, a], ["7", "8", "9"])))


def test_criterio_de_outra_edicao_e_recusado(digitacao, ficha):
    edicao, jurado, projetos = ficha
    ensaio = cadastro.edicao(nome="Ensaio 2026/2")
    alheio = Criterio.objects.create(edicao=ensaio, nome="Alheio", ordem=1)
    a, b, _ = _criterios(edicao)
    _recusado(digitacao.post(_passo2(jurado), _post(projetos[0], [a, b, alheio], ["7", "8", "9"])))


def test_formset_exige_os_criterios_da_edicao():
    """O clean() do formset, sozinho: o queryset do campo e o min/max não bastam
    se a linha chega sem critério (form já inválido)."""
    from banca.admin import NotaInline
    from django.contrib import admin
    from django.test import RequestFactory

    edicao, turma, projetos = fabricas.cenario(criterios=2)
    jurado = fabricas.jurado(edicao, turma)
    request = RequestFactory().get(f"/?jurado={jurado.pk}")
    request.user = User.objects.create_superuser("root", "r@example.com", "senha-forte-123")
    inline = NotaInline(Avaliacao, admin.site)
    formset_class = inline.get_formset(request, None)
    a, b = _criterios(edicao)
    instancia = Avaliacao(jurado=jurado)
    dados = {k: v for k, v in _post(projetos[0], [a, b], ["7", "8"]).items() if k != "projeto"}
    assert formset_class(dados, instance=instancia, prefix="notas").is_valid()
    dados["notas-1-criterio"] = a.pk
    formset = formset_class(dados, instance=instancia, prefix="notas")
    assert not formset.is_valid()
    assert "uma nota para cada critério" in str(formset.non_form_errors())


def test_projeto_de_outra_edicao_e_recusado(digitacao, ficha):
    edicao, jurado, _ = ficha
    _, _, alheios = fabricas.cenario(nome="Ensaio 2026/2", sigla="GTUR")
    _recusado(digitacao.post(_passo2(jurado), _post(alheios[0], _criterios(edicao), ["7"] * 3)))


def test_projeto_fora_das_turmas_do_jurado_e_recusado(digitacao, ficha):
    edicao, jurado, _ = ficha
    outro = cadastro.projeto(cadastro.turma(edicao, cadastro.curso("GTUR")), status=fabricas.PUBLICADO)
    _recusado(digitacao.post(_passo2(jurado), _post(outro, _criterios(edicao), ["7"] * 3)))


def test_projeto_nao_publicado_e_recusado(digitacao, ficha):
    edicao, jurado, projetos = ficha
    rascunho = cadastro.projeto(projetos[0].turma, titulo="Rascunho", status=Projeto.Status.EM_REVISAO)
    _recusado(digitacao.post(_passo2(jurado), _post(rascunho, _criterios(edicao), ["7"] * 3)))


def test_edicao_sem_criterios_e_recusada_no_formulario(digitacao):
    edicao, turma, projetos = fabricas.cenario(criterios=0)
    jurado = fabricas.jurado(edicao, turma)
    _recusado(
        digitacao.post(_passo2(jurado), _post(projetos[0], [], [])), "A edição não tem critérios cadastrados."
    )


def test_duplicata_e_recusada_com_a_mensagem(digitacao, ficha):
    edicao, jurado, projetos = ficha
    fabricas.avaliar(jurado, projetos[0], [7, 8, 9])
    resposta = digitacao.post(_passo2(jurado), _post(projetos[0], _criterios(edicao), ["1"] * 3))
    assert resposta.status_code == 200
    assert MENSAGEM_DUPLICATA in resposta.content.decode()
    assert Avaliacao.objects.count() == 1 and Nota.objects.count() == 3


# --- Alterar ----------------------------------------------------------------------------------


@pytest.fixture
def digitada(ficha):
    edicao, jurado, projetos = ficha
    avaliacao = fabricas.avaliar(jurado, projetos[0], [7, 8, 9], usuario=fabricas.digitador("carla"))
    return edicao, avaliacao


def _post_alteracao(avaliacao, valores):
    notas = list(avaliacao.notas.order_by("criterio__ordem"))
    dados = _post(
        avaliacao.projeto, [n.criterio for n in notas], valores, inicial=len(notas), ids=[n.pk for n in notas]
    )
    del dados["projeto"]  # só leitura na alteração
    return dados


def _change(avaliacao):
    return reverse("admin:banca_avaliacao_change", args=[avaliacao.pk])


def test_alterar_nota_registra_quem_alterou(digitacao, barbara, digitada):
    _, avaliacao = digitada
    antes = Avaliacao.objects.get(pk=avaliacao.pk)
    resposta = digitacao.post(_change(avaliacao), _post_alteracao(avaliacao, ["7", "6,5", "9"]))
    assert resposta.status_code == 302
    depois = Avaliacao.objects.get(pk=avaliacao.pk)
    assert depois.alterado_por == barbara and depois.alterado_em is not None
    assert (depois.digitado_por_id, depois.digitado_em) == (antes.digitado_por_id, antes.digitado_em)
    assert avaliacao.notas.get(criterio__ordem=2).valor == Decimal("6.5")


def test_alterar_nao_muda_jurado_nem_projeto(digitacao, digitada, ficha):
    _, avaliacao = digitada
    outro = fabricas.jurado(ficha[0], ficha[2][0].turma, nome="Bia")
    dados = _post_alteracao(avaliacao, ["7", "8", "9"])
    dados.update(jurado=outro.pk, projeto=ficha[2][1].pk)
    corpo = digitacao.get(_change(avaliacao)).content.decode()
    assert 'name="projeto"' not in corpo and 'name="jurado"' not in corpo
    assert 'name="notas-0-valor"' in corpo and "DELETE" not in corpo
    assert digitacao.post(_change(avaliacao), dados).status_code == 302
    depois = Avaliacao.objects.get(pk=avaliacao.pk)
    assert (depois.jurado_id, depois.projeto_id) == (avaliacao.jurado_id, avaliacao.projeto_id)


def test_sem_apagar_nota_nem_para_o_superusuario(admin_client, digitada):
    corpo = admin_client.get(_change(digitada[1])).content.decode()
    assert 'name="notas-0-valor"' in corpo and "notas-0-DELETE" not in corpo


def test_salvar_sem_mudanca_nao_mexe_em_nada(digitacao, digitada):
    edicao, avaliacao = digitada
    edicao.banca_conferida_em = timezone.now()
    edicao.save()
    antes = Avaliacao.objects.values().get(pk=avaliacao.pk)
    notas = list(Nota.objects.values().order_by("pk"))
    resposta = digitacao.post(_change(avaliacao), _post_alteracao(avaliacao, ["7,0", "8", "9"]), follow=True)
    assert resposta.status_code == 200
    assert Avaliacao.objects.values().get(pk=avaliacao.pk) == antes
    assert list(Nota.objects.values().order_by("pk")) == notas
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is not None
    assert CONFERENCIA_DESFEITA not in [str(m) for m in get_messages(resposta.wsgi_request)]


def test_alterar_com_conferencia_desfaz_e_avisa(digitacao, digitada):
    edicao, avaliacao = digitada
    edicao.banca_conferida_em = timezone.now()
    edicao.save()
    resposta = digitacao.post(_change(avaliacao), _post_alteracao(avaliacao, ["7", "8", "2"]), follow=True)
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None
    assert CONFERENCIA_DESFEITA in resposta.content.decode()


def test_edicao_conferida_nao_recebe_ficha_nova(digitacao, digitada, ficha):
    """Decisão do coordenador (#55): passo 1 e ?jurado= só de edição não conferida."""
    edicao, _ = digitada
    jurado = ficha[1]
    edicao.banca_conferida_em = timezone.now()
    edicao.save()
    assert f'value="{jurado.pk}"' not in digitacao.get(ADD).content.decode()
    assert digitacao.get(_passo2(jurado))["Location"] == ADD
    resposta = digitacao.post(_passo2(jurado), _post(ficha[2][1], _criterios(edicao), ["5"] * 3))
    assert resposta.status_code == 302 and resposta["Location"] == ADD
    assert Avaliacao.objects.count() == 1
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is not None


def test_criar_sem_conferencia_nao_avisa(digitacao, ficha):
    edicao, jurado, projetos = ficha
    resposta = digitacao.post(_passo2(jurado), _post(projetos[0], _criterios(edicao), ["5"] * 3), follow=True)
    assert Avaliacao.objects.count() == 1
    assert CONFERENCIA_DESFEITA not in resposta.content.decode()


def test_alterar_sem_conferencia_nao_avisa(digitacao, digitada):
    _, avaliacao = digitada
    resposta = digitacao.post(_change(avaliacao), _post_alteracao(avaliacao, ["1", "8", "9"]), follow=True)
    assert Avaliacao.objects.get(pk=avaliacao.pk).alterado_por is not None
    assert CONFERENCIA_DESFEITA not in resposta.content.decode()


def test_apagar_sem_conferencia_nao_avisa(admin_client, digitada):
    _, avaliacao = digitada
    url = reverse("admin:banca_avaliacao_delete", args=[avaliacao.pk])
    resposta = admin_client.post(url, {"post": "yes"}, follow=True)
    assert not Avaliacao.objects.exists()
    assert CONFERENCIA_DESFEITA not in resposta.content.decode()


def test_apagar_em_lote_sem_conferencia_nao_avisa(admin_client, digitada):
    _, avaliacao = digitada
    dados = {"action": "delete_selected", "_selected_action": [avaliacao.pk], "post": "yes"}
    resposta = admin_client.post(reverse("admin:banca_avaliacao_changelist"), dados, follow=True)
    assert not Avaliacao.objects.exists()
    assert CONFERENCIA_DESFEITA not in resposta.content.decode()


def test_apagar_em_lote_de_outra_edicao_nao_avisa_nem_desfaz(admin_client, digitada):
    """Edição A conferida; o lote apaga só uma avaliação da edição B: sem aviso."""
    edicao, avaliacao = digitada
    outra, turma_o, projetos_o = fabricas.cenario(nome="Ensaio 2026/2", sigla="GTUR", criterios=3)
    alheia = fabricas.avaliar(fabricas.jurado(outra, turma_o), projetos_o[0], [1, 2, 3])
    edicao.refresh_from_db()
    edicao.banca_conferida_em = timezone.now()
    edicao.save()
    dados = {"action": "delete_selected", "_selected_action": [alheia.pk], "post": "yes"}
    resposta = admin_client.post(reverse("admin:banca_avaliacao_changelist"), dados, follow=True)
    assert CONFERENCIA_DESFEITA not in resposta.content.decode()
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is not None


def test_alterar_nota_para_invalida_nao_grava(digitacao, digitada):
    _, avaliacao = digitada
    resposta = digitacao.post(_change(avaliacao), _post_alteracao(avaliacao, ["7", "11", "9"]))
    assert resposta.status_code == 200
    assert avaliacao.notas.get(criterio__ordem=2).valor == Decimal("8")
    assert Avaliacao.objects.get(pk=avaliacao.pk).alterado_por is None


# --- Apagar e permissões ----------------------------------------------------------------------------


def test_grupo_nao_apaga(digitacao, digitada):
    _, avaliacao = digitada
    url = reverse("admin:banca_avaliacao_delete", args=[avaliacao.pk])
    assert digitacao.get(url).status_code == 403
    assert digitacao.post(url, {"post": "yes"}).status_code == 403
    lista = digitacao.get(reverse("admin:banca_avaliacao_changelist"))
    assert lista.status_code == 200 and "delete_selected" not in lista.content.decode()
    assert Avaliacao.objects.filter(pk=avaliacao.pk).exists()


def test_superusuario_apaga_e_desfaz_a_conferencia(admin_client, digitada):
    edicao, avaliacao = digitada
    edicao.banca_conferida_em = timezone.now()
    edicao.save()
    url = reverse("admin:banca_avaliacao_delete", args=[avaliacao.pk])
    resposta = admin_client.post(url, {"post": "yes"}, follow=True)
    assert not Avaliacao.objects.exists() and not Nota.objects.exists()
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None
    assert CONFERENCIA_DESFEITA in resposta.content.decode()


def test_superusuario_apaga_em_lote_e_desfaz_a_conferencia(admin_client, digitada):
    edicao, avaliacao = digitada
    edicao.banca_conferida_em = timezone.now()
    edicao.save()
    dados = {"action": "delete_selected", "_selected_action": [avaliacao.pk], "post": "yes"}
    resposta = admin_client.post(reverse("admin:banca_avaliacao_changelist"), dados, follow=True)
    assert not Avaliacao.objects.exists()
    edicao.refresh_from_db()
    assert edicao.banca_conferida_em is None
    assert CONFERENCIA_DESFEITA in resposta.content.decode()


def test_superusuario_digita_tambem(admin_client, superusuario, ficha):
    edicao, jurado, projetos = ficha
    resposta = admin_client.post(_passo2(jurado), _post(projetos[1], _criterios(edicao), ["0", "10", "5,5"]))
    assert resposta.status_code == 302
    assert Avaliacao.objects.get().digitado_por == superusuario


def test_lista_mostra_jurado_projeto_e_digitador(digitacao, digitada):
    _, avaliacao = digitada
    corpo = digitacao.get(reverse("admin:banca_avaliacao_changelist") + "?q=Projeto+0").content.decode()
    assert f"#{avaliacao.projeto_id} — Projeto 0" in corpo and "carla" in corpo


def test_anonimo_vai_para_o_login(client):
    resposta = client.get(ADD)
    assert resposta.status_code == 302 and "/login/" in resposta["Location"]


# --- Revisão do #55: POST adulterado, corrida, ordem das linhas, consultas, formato ------------


def _sem_500_nada_gravado(resposta, avaliacoes=0, notas=0):
    assert resposta.status_code == 200, resposta.status_code
    assert Avaliacao.objects.count() == avaliacoes and Nota.objects.count() == notas


@pytest.fixture
def outra_ficha(ficha):
    """Uma avaliação já gravada (de outro projeto), dona dos ids "alheios"."""
    edicao, jurado, projetos = ficha
    return fabricas.avaliar(jurado, projetos[1], [1, 2, 3], usuario=fabricas.digitador("carla"))


@pytest.mark.parametrize("k", [1, 3])
def test_add_com_ids_de_notas_alheias_e_recusado(digitacao, ficha, outra_ficha, k):
    edicao, jurado, projetos = ficha
    alheias = list(outra_ficha.notas.order_by("criterio__ordem").values_list("pk", flat=True))
    dados = _post(projetos[0], _criterios(edicao), ["2", "10", "10"], inicial=k)
    for i in range(k):
        dados[f"notas-{i}-id"] = alheias[i]
    resposta = digitacao.post(_passo2(jurado), dados)
    _sem_500_nada_gravado(resposta, avaliacoes=1, notas=3)
    assert LINHAS in resposta.content.decode()


def test_add_com_initial_forms_forjado_sem_id_e_recusado(digitacao, ficha):
    edicao, jurado, projetos = ficha
    resposta = digitacao.post(_passo2(jurado), _post(projetos[0], _criterios(edicao), ["7"] * 3, inicial=3))
    _sem_500_nada_gravado(resposta)


def _alteracao_recusada(digitacao, avaliacao, dados):
    antes = list(Nota.objects.values().order_by("pk"))
    resposta = digitacao.post(_change(avaliacao), dados)
    assert resposta.status_code == 200, resposta.status_code
    assert LINHAS in resposta.content.decode()
    assert list(Nota.objects.values().order_by("pk")) == antes
    assert Avaliacao.objects.get(pk=avaliacao.pk).alterado_por is None


def test_change_com_ids_de_outra_avaliacao_e_recusado(digitacao, digitada, outra_ficha):
    _, avaliacao = digitada
    dados = _post_alteracao(avaliacao, ["1", "1", "1"])
    for i, pk in enumerate(outra_ficha.notas.order_by("criterio__ordem").values_list("pk", flat=True)):
        dados[f"notas-{i}-id"] = pk
    _alteracao_recusada(digitacao, avaliacao, dados)


def test_change_trocando_criterio_entre_linhas_e_recusado(digitacao, digitada):
    _, avaliacao = digitada
    dados = _post_alteracao(avaliacao, ["7", "8", "9"])
    dados["notas-0-criterio"], dados["notas-1-criterio"] = dados["notas-1-criterio"], dados["notas-0-criterio"]
    _alteracao_recusada(digitacao, avaliacao, dados)


def test_change_com_initial_forms_zero_e_recusado(digitacao, digitada):
    _, avaliacao = digitada
    dados = _post_alteracao(avaliacao, ["1", "2", "3"])
    dados["notas-INITIAL_FORMS"] = 0
    for i in range(3):
        del dados[f"notas-{i}-id"]
    _alteracao_recusada(digitacao, avaliacao, dados)


def test_change_com_id_repetido_e_recusado(digitacao, digitada):
    _, avaliacao = digitada
    dados = _post_alteracao(avaliacao, ["1", "2", "3"])
    dados["notas-2-id"] = dados["notas-1-id"]
    _alteracao_recusada(digitacao, avaliacao, dados)


def test_duplo_clique_volta_com_a_mensagem_sem_500(digitacao, ficha):
    """Corrida: a 1ª validação não vê a duplicata (a outra requisição ainda não
    tinha gravado); o índice único recusa e o admin valida de novo."""
    from unittest import mock

    edicao, jurado, projetos = ficha
    fabricas.avaliar(jurado, projetos[0], [7, 8, 9])
    original = Avaliacao.validate_constraints
    chamadas = []

    def primeira_cega(self, exclude=None):
        chamadas.append(1)
        if len(chamadas) > 1:
            return original(self, exclude=exclude)

    with mock.patch.object(Avaliacao, "validate_constraints", primeira_cega):
        resposta = digitacao.post(_passo2(jurado), _post(projetos[0], _criterios(edicao), ["1"] * 3))
    assert len(chamadas) == 2
    assert resposta.status_code == 200 and MENSAGEM_DUPLICATA in resposta.content.decode()
    assert Avaliacao.objects.count() == 1 and Nota.objects.count() == 3


@pytest.fixture
def ficha_embaralhada():
    """Critérios criados fora da ordem da ficha (pk não segue `ordem`)."""
    from votacao.servicos import encerrar_votacao, abrir_votacao
    from cadastro.models import Edicao

    for aberta in Edicao.objects.filter(votacao_aberta_em__isnull=False, votacao_encerrada_em__isnull=True):
        encerrar_votacao(aberta.pk)
    edicao = cadastro.edicao(nome="2026/2")
    turma = cadastro.turma(edicao, cadastro.curso("DSM"))
    projeto = cadastro.projeto(turma, titulo="Projeto 0", status=fabricas.PUBLICADO)
    for nome, ordem in [("Gama", 3), ("Alfa", 1), ("Beta", 2)]:
        Criterio.objects.create(edicao=edicao, nome=nome, ordem=ordem)
    assert abrir_votacao(edicao.pk) is None
    return edicao, fabricas.jurado(edicao, turma), projeto


def _linhas(corpo, edicao):
    """(critério, valor) de cada linha do inline, na ordem do HTML."""
    import re

    nomes = {str(c.pk): c.nome for c in Criterio.objects.filter(edicao=edicao)}
    linhas = []
    for i in range(3):
        oculto = re.search(rf'<input[^>]*name="notas-{i}-criterio"[^>]*>', corpo).group(0)
        criterio = re.search(r'value="(\d+)"', oculto).group(1)
        tag = re.search(rf'<input[^>]*name="notas-{i}-valor"[^>]*>', corpo).group(0)
        valor = re.search(r'value="([^"]*)"', tag)
        linhas.append((nomes[criterio], valor and valor.group(1)))
    posicoes = [corpo.index(nome) for nome, _ in linhas]
    assert posicoes == sorted(posicoes)  # o nome visível acompanha a linha
    return linhas


def test_linhas_na_ordem_da_ficha_no_add_e_no_change(digitacao, ficha_embaralhada):
    edicao, jurado, projeto = ficha_embaralhada
    assert [nome for nome, _ in _linhas(digitacao.get(_passo2(jurado)).content.decode(), edicao)] == [
        "Alfa",
        "Beta",
        "Gama",
    ]
    avaliacao = Avaliacao.objects.create(jurado=jurado, projeto=projeto, digitado_por=fabricas.digitador("carla"))
    for nome, valor in [("Gama", "3.0"), ("Alfa", "1.0"), ("Beta", "2.0")]:
        Nota.objects.create(avaliacao=avaliacao, criterio=Criterio.objects.get(edicao=edicao, nome=nome), valor=valor)
    linhas = _linhas(digitacao.get(_change(avaliacao)).content.decode(), edicao)
    assert linhas == [("Alfa", "1,0"), ("Beta", "2,0"), ("Gama", "3,0")]


def test_lista_com_numero_fixo_de_consultas(digitacao):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    edicao, turma, projetos = fabricas.cenario(criterios=1, projetos=1)
    url = reverse("admin:banca_avaliacao_changelist")
    contagens = []
    for total in (2, 12):
        while edicao.jurados.count() < total:
            j = fabricas.jurado(edicao, turma, nome=f"Jurado {edicao.jurados.count()}")
            fabricas.avaliar(j, projetos[0], [5])
        with CaptureQueriesContext(connection) as consultas:
            assert digitacao.get(url).status_code == 200
        contagens.append(len(consultas))
    assert contagens[0] == contagens[1], contagens


@pytest.mark.parametrize("valor, gravado", [("7,5", "7.5"), ("7.5", "7.5"), (" 7,5 ", "7.5"), ("10", "10"), ("0", "0")])
def test_formatos_de_ficha_aceitos(digitacao, ficha, valor, gravado):
    edicao, jurado, projetos = ficha
    assert digitacao.post(_passo2(jurado), _post(projetos[0], _criterios(edicao), [valor, "5", "5"])).status_code == 302
    assert Nota.objects.get(criterio__ordem=1).valor == Decimal(gravado)
