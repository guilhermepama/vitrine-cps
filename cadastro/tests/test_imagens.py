"""Critérios de aceite "Imagens" — guardrail 14 (specs/01-cadastro.md)."""

import re

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from cadastro.imagens import TAMANHO_MAXIMO, validar_imagem
from cadastro.models import ImagemProjeto
from cadastro.tests import fabricas


def test_jpg_que_nao_e_imagem_e_recusado():
    falso = SimpleUploadedFile("foto.jpg", b"isto nao e uma imagem", content_type="image/jpeg")
    with pytest.raises(ValidationError):
        validar_imagem(falso)


def test_gif_e_recusado():
    with pytest.raises(ValidationError):
        validar_imagem(fabricas.imagem("GIF", "foto.gif"))


@pytest.mark.parametrize("formato", ["PNG", "JPEG", "WEBP"])
def test_formatos_aceitos(formato):
    validar_imagem(fabricas.imagem(formato))


def test_imagem_acima_de_3mb_e_recusada():
    arquivo = fabricas.imagem()
    arquivo.size = TAMANHO_MAXIMO + 1
    with pytest.raises(ValidationError):
        validar_imagem(arquivo)


@pytest.mark.django_db
def test_nome_gerado_pelo_servidor_com_extensao_do_formato_real(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    png_disfarcado = fabricas.imagem("PNG", "../../meu arquivo.jpg")
    p = fabricas.projeto(capa=png_disfarcado)
    assert re.fullmatch(r"projetos/[0-9a-f]{32}\.png", p.capa.name)
    assert "meu" not in p.capa.name


@pytest.mark.django_db
def test_imagem_extra_tambem_tem_nome_gerado(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    img = ImagemProjeto.objects.create(projeto=fabricas.projeto(), arquivo=fabricas.imagem("JPEG", "x.png"))
    assert re.fullmatch(r"projetos/[0-9a-f]{32}\.jpg", img.arquivo.name)


@pytest.mark.django_db
def test_validacao_roda_no_full_clean_do_model(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    p = fabricas.projeto()
    p.capa = SimpleUploadedFile("x.jpg", b"falso", content_type="image/jpeg")
    with pytest.raises(ValidationError) as erro:
        p.full_clean()
    assert "capa" in erro.value.message_dict


def _mpo():
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(
        buffer, format="MPO", save_all=True, append_images=[Image.new("RGB", (20, 20), "blue")]
    )
    return SimpleUploadedFile("IMG_2026.jpg", buffer.getvalue(), content_type="image/jpeg")


def test_foto_de_celular_mpo_e_aceita():
    validar_imagem(_mpo())


@pytest.mark.django_db
def test_foto_mpo_e_gravada_como_jpg(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    p = fabricas.projeto(capa=_mpo())
    assert re.fullmatch(r"projetos/[0-9a-f]{32}\.jpg", p.capa.name)


@pytest.mark.django_db
def test_salvar_sem_validar_arquivo_invalido_nao_grava(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    with pytest.raises(ValidationError):
        fabricas.projeto(capa=SimpleUploadedFile("x.jpg", b"falso", content_type="image/jpeg"))
    assert not any(tmp_path.rglob("*.*"))
