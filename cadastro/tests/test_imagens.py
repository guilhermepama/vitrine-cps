"""Critérios de aceite "Imagens" — guardrail 14 (specs/01-cadastro.md)."""

import re

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from cadastro.imagens import ORIENTACAO, TAMANHO_MAXIMO, validar_imagem
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


# --- Metadados (GPS) e resolução --------------------------------------------------------

GPS = 0x8825


def _com_metadados(formato="JPEG", orientacao=6):
    import io

    from PIL import Image, PngImagePlugin

    exif = Image.Exif()
    exif[0x0110] = "Celular do aluno"  # modelo do aparelho
    exif[ORIENTACAO] = orientacao
    exif.get_ifd(GPS).update({1: "S", 2: (20.0, 44.0, 12.0), 3: "W", 4: (48.0, 54.0, 3.0)})
    buffer = io.BytesIO()
    imagem = Image.new("RGB", (40, 20), "green")
    if formato == "PNG":
        texto = PngImagePlugin.PngInfo()
        texto.add_text("Comment", "Olímpia, casa do aluno")
        imagem.save(buffer, "PNG", exif=exif.tobytes(), pnginfo=texto)
    else:
        imagem.save(buffer, formato, exif=exif.tobytes())
    return SimpleUploadedFile(f"foto.{formato.lower()}", buffer.getvalue(), content_type="image/jpeg")


def _abrir_gravada(campo):
    from PIL import Image

    campo.open("rb")
    try:
        imagem = Image.open(campo)
        imagem.load()
        return imagem
    finally:
        campo.close()


@pytest.mark.django_db
@pytest.mark.parametrize("formato", ["JPEG", "WEBP"])
def test_capa_e_gravada_sem_gps_e_com_a_orientacao(settings, tmp_path, formato):
    settings.MEDIA_ROOT = tmp_path
    p = fabricas.projeto(capa=_com_metadados(formato))
    exif = _abrir_gravada(p.capa).getexif()
    assert GPS not in exif and 0x0110 not in exif
    assert exif.get(ORIENTACAO) == 6  # a foto não aparece deitada
    gravado = next(tmp_path.rglob("*.*")).read_bytes()
    assert b"Celular do aluno" not in gravado


@pytest.mark.django_db
def test_imagem_extra_tambem_sai_sem_gps(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    img = ImagemProjeto.objects.create(projeto=fabricas.projeto(), arquivo=_com_metadados())
    assert GPS not in _abrir_gravada(img.arquivo).getexif()


@pytest.mark.django_db
def test_png_perde_exif_e_textos(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    p = fabricas.projeto(capa=_com_metadados("PNG"))
    imagem = _abrir_gravada(p.capa)
    assert not imagem.getexif() and "Comment" not in imagem.info
    assert b"casa do aluno" not in next(tmp_path.rglob("*.*")).read_bytes()


@pytest.mark.django_db
def test_jpeg_nao_e_redimensionado_nem_muda_de_formato(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    p = fabricas.projeto(capa=_com_metadados())
    imagem = _abrir_gravada(p.capa)
    assert (imagem.format, imagem.size) == ("JPEG", (40, 20))
    assert p.capa.name.endswith(".jpg")


@pytest.mark.django_db
def test_mpo_sai_sem_metadados_e_continua_jpg(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    p = fabricas.projeto(capa=_mpo())
    assert re.fullmatch(r"projetos/[0-9a-f]{32}\.jpg", p.capa.name)
    assert _abrir_gravada(p.capa).format == "JPEG"


@pytest.mark.django_db
def test_imagem_ja_gravada_nao_e_regravada(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    p = fabricas.projeto(capa=_com_metadados())
    nome = p.capa.name
    p.titulo = "Outro título"
    p.save()
    assert p.capa.name == nome and len(list(tmp_path.rglob("*.*"))) == 1


def test_resolucao_acima_do_teto_e_recusada():
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("1", (5001, 5000)).save(buffer, "PNG")  # 25 MP + 5000 px, poucos KB
    arquivo = SimpleUploadedFile("grande.png", buffer.getvalue(), content_type="image/png")
    assert arquivo.size < TAMANHO_MAXIMO
    with pytest.raises(ValidationError) as erro:
        validar_imagem(arquivo)
    assert erro.value.code == "pixels"


@pytest.mark.django_db
def test_comentario_do_jpeg_nao_vaza(settings, tmp_path):
    import io

    from PIL import Image

    settings.MEDIA_ROOT = tmp_path
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(buffer, "JPEG", comment=b"Rua do aluno, 123")
    fabricas.projeto(capa=SimpleUploadedFile("c.jpg", buffer.getvalue(), content_type="image/jpeg"))
    assert b"Rua do aluno" not in next(tmp_path.rglob("*.*")).read_bytes()


def _jpeg_cortado():
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.effect_noise((200, 200), 64).convert("RGB").save(buffer, "JPEG")
    return SimpleUploadedFile("cortada.jpg", buffer.getvalue()[:-2000], content_type="image/jpeg")


def test_jpeg_cortado_e_recusado_na_validacao():
    """Upload interrompido no celular: o `verify()` deixava passar, e a
    limpeza quebrava com 500 na hora de gravar."""
    with pytest.raises(ValidationError) as erro:
        validar_imagem(_jpeg_cortado())
    assert erro.value.code == "formato"


def _png_grande_demais():
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("1", (5001, 5000)).save(buffer, "PNG")
    return SimpleUploadedFile("g.png", buffer.getvalue(), content_type="image/png")


@pytest.mark.django_db
@pytest.mark.parametrize("arquivo", [_jpeg_cortado, _png_grande_demais])
def test_salvar_sem_validar_jpeg_cortado_ou_grande_demais_nao_grava(settings, tmp_path, arquivo):
    settings.MEDIA_ROOT = tmp_path
    with pytest.raises(ValidationError):
        fabricas.projeto(capa=arquivo())
    assert not any(tmp_path.rglob("*.*"))


# --- Orientação malformada (revisão posterior do #48) -------------------------------


def _jpeg_com_orientacao_em_texto():
    """JPEG com a tag de orientação gravada como texto ("seis"). O `verify()`
    aceita; antes, a limpeza quebrava com struct.error (500)."""
    import io
    import struct

    from PIL import Image

    ifd = struct.pack("<H", 1) + struct.pack("<HHII", ORIENTACAO, 2, 5, 26) + struct.pack("<I", 0)
    exif = b"Exif\x00\x00" + b"II*\x00" + struct.pack("<I", 8) + ifd + b"seis\x00"
    buffer = io.BytesIO()
    Image.new("RGB", (40, 20), "green").save(buffer, "JPEG", exif=exif)
    return SimpleUploadedFile("torta.jpg", buffer.getvalue(), content_type="image/jpeg")


@pytest.mark.django_db
def test_orientacao_em_texto_e_descartada_sem_erro(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    p = fabricas.projeto(capa=_jpeg_com_orientacao_em_texto())
    assert ORIENTACAO not in _abrir_gravada(p.capa).getexif()


@pytest.mark.django_db
@pytest.mark.parametrize("valor", [0, 9, 99])
def test_orientacao_fora_de_1_a_8_e_descartada(settings, tmp_path, valor):
    settings.MEDIA_ROOT = tmp_path
    p = fabricas.projeto(capa=_com_metadados(orientacao=valor))
    assert ORIENTACAO not in _abrir_gravada(p.capa).getexif()


@pytest.mark.django_db
def test_falha_ao_regravar_vira_validation_error_e_nada_e_gravado(settings, tmp_path, monkeypatch):
    import struct

    from cadastro import imagens

    def quebra(*args, **kwargs):
        raise struct.error("metadado malformado")

    settings.MEDIA_ROOT = tmp_path
    monkeypatch.setattr(imagens, "_sem_metadados", quebra)
    with pytest.raises(ValidationError) as erro:
        fabricas.projeto(capa=_com_metadados())
    assert erro.value.code == "formato"
    assert not any(tmp_path.rglob("*.*"))
