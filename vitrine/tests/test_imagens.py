"""Critérios de aceite "Imagens" (specs/02-vitrine-publica.md) — guardrail 14."""

import logging
import os
import re
import threading
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, transaction

from cadastro.imagens import TAMANHO_MAXIMO
from cadastro.models import ImagemProjeto, Projeto
from cadastro.tests import fabricas
from vitrine import servicos
from vitrine.forms import ImagemUploadForm
from vitrine.tests import auxiliares as aux


def enviar(client, token, tipo, arquivo, legenda=""):
    return client.post(
        f"/grupo/editar/{token}/imagem/", {"tipo": tipo, "arquivo": arquivo, "legenda": legenda}
    )


def _extras(projeto, quantas):
    for i in range(quantas):
        ImagemProjeto.objects.create(projeto=projeto, arquivo=fabricas.imagem(), ordem=i)


@pytest.mark.django_db
def test_capa_valida_grava_e_nome_gerado_pelo_servidor(client, settings):
    p, token = aux.projeto_com_link()
    r = enviar(client, token, "capa", fabricas.imagem("PNG", "../../minha foto.jpg"))
    assert r.status_code == 302
    p.refresh_from_db()
    assert re.fullmatch(r"projetos/[0-9a-f]{32}\.png", p.capa.name)  # extensão do formato real
    assert "minha" not in p.capa.name


@pytest.mark.django_db
def test_extra_valida_cria_imagem_com_legenda(client):
    p, token = aux.projeto_com_link()
    assert enviar(client, token, "extra", fabricas.imagem(), "Tela inicial").status_code == 302
    imagem = p.imagens.get()
    assert imagem.legenda == "Tela inicial"


@pytest.mark.django_db
def test_trocar_a_capa_apaga_o_arquivo_antigo_depois_do_commit(
    client, settings, django_capture_on_commit_callbacks
):
    p, token = aux.projeto_com_link()
    aux.com_capa(p)
    antigo = Path(settings.MEDIA_ROOT) / p.capa.name
    assert antigo.exists()
    with django_capture_on_commit_callbacks(execute=True):
        assert enviar(client, token, "capa", fabricas.imagem()).status_code == 302
    p.refresh_from_db()
    assert not antigo.exists()
    assert (Path(settings.MEDIA_ROOT) / p.capa.name).exists()


@pytest.mark.django_db
def test_se_a_transacao_for_desfeita_o_arquivo_antigo_continua(settings, django_capture_on_commit_callbacks):
    p, token = aux.projeto_com_link()
    aux.com_capa(p)
    nome = p.capa.name
    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                servicos.enviar_imagem(p.pk, token, "capa", fabricas.imagem())
                raise RuntimeError("desfaz tudo")
    p.refresh_from_db()
    assert p.capa.name == nome
    assert (Path(settings.MEDIA_ROOT) / nome).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("tipo", ["capa", "extra"])
def test_erro_depois_do_upload_nao_deixa_arquivo_orfao(settings, monkeypatch, tipo):
    from django.db import DatabaseError
    from django.db.models import Model

    p, token = aux.projeto_com_link()
    pasta = Path(settings.MEDIA_ROOT) / "projetos"
    antes = set(pasta.glob("*")) if pasta.exists() else set()

    def falhar_depois_de_gravar(original):
        def envolvido(self, *args, **kwargs):
            original(self, *args, **kwargs)  # o arquivo já subiu (pre_save)
            raise DatabaseError("falha simulada")

        return envolvido

    monkeypatch.setattr(Model, "_do_update", falhar_depois_de_gravar(Model._do_update))
    monkeypatch.setattr(Model, "_do_insert", falhar_depois_de_gravar(Model._do_insert))
    with pytest.raises(DatabaseError):
        servicos.enviar_imagem(p.pk, token, tipo, fabricas.imagem())
    monkeypatch.undo()

    depois = set(pasta.glob("*")) if pasta.exists() else set()
    assert depois == antes, "o arquivo novo ficou órfão no storage"
    p.refresh_from_db()
    assert p.imagens.count() == 0 and not p.capa


@pytest.mark.django_db
def test_ordem_nao_repete_depois_de_remover(client):
    p, token = aux.projeto_com_link()
    _extras(p, 3)
    primeira = p.imagens.order_by("ordem").first()
    assert client.post(f"/grupo/editar/{token}/imagem/{primeira.pk}/remover/").status_code == 302
    assert enviar(client, token, "extra", fabricas.imagem()).status_code == 302
    ordens = list(p.imagens.order_by("ordem", "id").values_list("ordem", flat=True))
    assert len(set(ordens)) == len(ordens) == 3


@pytest.mark.django_db
def test_tipo_invalido_nao_repete_a_entrada(client):
    p, token = aux.projeto_com_link()
    r = enviar(client, token, "<b>banner</b>", fabricas.imagem())
    assert r.status_code == 400
    html = r.content.decode()
    assert "Tipo de imagem inválido." in html and "banner" not in html


@pytest.mark.django_db
def test_falha_ao_apagar_nao_desfaz_a_gravacao_e_nao_vaza_o_token(
    client, monkeypatch, caplog, django_capture_on_commit_callbacks
):
    class StorageQueQuebra:
        def delete(self, nome):
            raise OSError("bucket fora do ar")

    p, token = aux.projeto_com_link()
    aux.com_capa(p)
    nome_antigo = p.capa.name
    monkeypatch.setattr(servicos, "default_storage", StorageQueQuebra())
    with caplog.at_level(logging.WARNING), django_capture_on_commit_callbacks(execute=True):
        r = enviar(client, token, "capa", fabricas.imagem())
    assert r.status_code == 302
    p.refresh_from_db()
    assert p.capa.name != nome_antigo  # a gravação valeu
    assert "Falha ao apagar" in caplog.text
    assert token not in caplog.text and aux.RA not in caplog.text


@pytest.mark.django_db
def test_setima_imagem_extra_e_recusada(client):
    p, token = aux.projeto_com_link()
    for _ in range(6):
        assert enviar(client, token, "extra", fabricas.imagem()).status_code == 302
    r = enviar(client, token, "extra", fabricas.imagem())
    assert r.status_code == 400
    assert p.imagens.count() == 6


@pytest.mark.django_db
def test_arquivo_que_nao_e_imagem_e_gif_sao_recusados(client):
    p, token = aux.projeto_com_link()
    falso = SimpleUploadedFile("foto.jpg", b"isto nao e uma imagem", content_type="image/jpeg")
    assert enviar(client, token, "extra", falso).status_code == 400
    assert enviar(client, token, "extra", fabricas.imagem("GIF", "foto.gif")).status_code == 400
    assert p.imagens.count() == 0 and not p.capa


def test_imagem_acima_de_3mb_e_recusada():
    arquivo = fabricas.imagem()
    arquivo.size = TAMANHO_MAXIMO + 1
    form = ImagemUploadForm({"tipo": "capa"}, {"arquivo": arquivo})
    assert not form.is_valid()


@pytest.mark.django_db
def test_imagem_acima_de_3mb_pelo_post_da_400_e_nao_grava(client):
    import io

    from PIL import Image

    # Ruído: o PNG não comprime, então passa de 3 MB de verdade.
    ruido = Image.frombytes("RGB", (1100, 1100), os.urandom(1100 * 1100 * 3))
    buffer = io.BytesIO()
    ruido.save(buffer, format="PNG")
    assert len(buffer.getvalue()) > TAMANHO_MAXIMO
    p, token = aux.projeto_com_link()
    arquivo = SimpleUploadedFile("grande.png", buffer.getvalue(), content_type="image/png")
    assert enviar(client, token, "capa", arquivo).status_code == 400
    p.refresh_from_db()
    assert p.imagens.count() == 0 and not p.capa


@pytest.mark.django_db
def test_mais_de_um_arquivo_na_mesma_requisicao_e_recusado(client):
    p, token = aux.projeto_com_link()
    r = client.post(
        f"/grupo/editar/{token}/imagem/",
        {"tipo": "extra", "arquivo": [fabricas.imagem(), fabricas.imagem()]},
    )
    assert r.status_code == 400
    assert p.imagens.count() == 0


@pytest.mark.django_db
def test_tipo_desconhecido_e_recusado(client):
    p, token = aux.projeto_com_link()
    assert enviar(client, token, "banner", fabricas.imagem()).status_code == 400


@pytest.mark.django_db
def test_remover_extra_do_proprio_projeto_apaga_o_arquivo(client, settings, django_capture_on_commit_callbacks):
    p, token = aux.projeto_com_link()
    _extras(p, 1)
    imagem = p.imagens.get()
    arquivo = Path(settings.MEDIA_ROOT) / imagem.arquivo.name
    with django_capture_on_commit_callbacks(execute=True):
        r = client.post(f"/grupo/editar/{token}/imagem/{imagem.pk}/remover/")
    assert r.status_code == 302
    assert p.imagens.count() == 0 and not arquivo.exists()


@pytest.mark.django_db
def test_remover_imagem_de_outro_projeto_da_404_e_nada_muda(client):
    p, token = aux.projeto_com_link()
    outro, _ = aux.projeto_com_link(edicao=p.turma.edicao, ra_hmac=aux.hash_ra("7654321"))
    _extras(outro, 1)
    alheia = outro.imagens.get()
    r = client.post(f"/grupo/editar/{token}/imagem/{alheia.pk}/remover/")
    assert r.status_code == 404
    assert outro.imagens.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("cenario", ["em_revisao", "publicado", "prazo", "votacao_aberta"])
def test_projeto_nao_editavel_da_403_no_upload_e_na_remocao(client, cenario):
    if cenario in ("em_revisao", "publicado"):
        status = Projeto.Status.EM_REVISAO if cenario == "em_revisao" else Projeto.Status.PUBLICADO
        p, token = aux.projeto_com_link(status=status)
    else:
        p, token = aux.projeto_com_link()
        (aux.prazo_vencido if cenario == "prazo" else aux.votacao_aberta)(p)
    _extras(p, 1)
    existente = p.imagens.get()
    assert enviar(client, token, "extra", fabricas.imagem()).status_code == 403
    assert enviar(client, token, "capa", fabricas.imagem()).status_code == 403
    assert client.post(f"/grupo/editar/{token}/imagem/{existente.pk}/remover/").status_code == 403
    p.refresh_from_db()
    assert p.imagens.count() == 1 and not p.capa


@pytest.mark.django_db(transaction=True)
def test_dois_uploads_simultaneos_com_5_extras_gravam_so_um():
    p, token = aux.projeto_com_link()
    _extras(p, 5)
    resultados = []
    largada = threading.Barrier(2)

    def enviar_extra():
        arquivo = fabricas.imagem()
        try:
            largada.wait(5)
            servicos.enviar_imagem(p.pk, token, "extra", arquivo)
            resultados.append("gravou")
        except servicos.LimiteDeImagens:
            resultados.append("limite")
        finally:
            connection.close()

    threads = [threading.Thread(target=enviar_extra) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(resultados) == ["gravou", "limite"]
    assert p.imagens.count() == 6
