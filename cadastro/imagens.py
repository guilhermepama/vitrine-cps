"""Validação, nome de arquivo e limpeza de metadados das imagens dos projetos
(guardrail 14)."""

import io
import uuid

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image

TAMANHO_MAXIMO = 3 * 1024 * 1024  # 3 MB
# Teto em pixels: a limpeza de metadados decodifica a imagem inteira na
# memória (~3 bytes por pixel). 25 MP cobre câmera de celular e DSLR comum.
PIXELS_MAXIMOS = 25_000_000
ORIENTACAO = 0x0112  # a única tag EXIF que sobrevive à limpeza
# MPO = JPEG com várias imagens, como muitos celulares salvam a foto: vira .jpg.
FORMATOS = {"JPEG": "jpg", "MPO": "jpg", "PNG": "png", "WEBP": "webp"}


def _ler(arquivo):
    """(formato real, pixels) lidos do conteúdo, sem decodificar a imagem."""
    try:
        arquivo.seek(0)
        with Image.open(arquivo) as imagem:
            formato, pixels = imagem.format, imagem.width * imagem.height
            imagem.verify()
    except Exception:
        return None, 0
    finally:
        arquivo.seek(0)
    return formato, pixels


def detectar_formato(arquivo):
    """Formato real do arquivo, lido do conteúdo (não da extensão nem do content_type)."""
    return _ler(arquivo)[0]


def _decodifica(arquivo):
    """A imagem inteira decodifica? O `verify()` não decodifica JPEG: uma foto
    cortada (upload interrompido no celular) passaria e quebraria na limpeza."""
    try:
        arquivo.seek(0)
        with Image.open(arquivo) as imagem:
            imagem.load()
    except Exception:
        return False
    finally:
        arquivo.seek(0)
    return True


def validar_imagem(arquivo):
    if arquivo.size > TAMANHO_MAXIMO:
        raise ValidationError("A imagem pode ter no máximo 3 MB.", code="tamanho")
    formato, pixels = _ler(arquivo)
    if formato not in FORMATOS:
        raise ValidationError("Envie uma imagem JPG, PNG ou WebP.", code="formato")
    if pixels > PIXELS_MAXIMOS:
        raise ValidationError("A imagem tem resolução grande demais.", code="pixels")
    if not _decodifica(arquivo):
        raise ValidationError("Envie uma imagem JPG, PNG ou WebP.", code="formato")


def remover_metadados(campo):
    """Regrava a imagem recém-enviada sem metadados (EXIF com GPS, data,
    aparelho; comentário do JPEG; textos do PNG). Só a orientação fica, para a foto não aparecer
    deitada. O bucket é público: o que sobe com a foto fica legível por
    qualquer um (fotos de alunos menores da Etec, inclusive).

    Não redimensiona nem muda o formato. JPEG é regravado com as mesmas
    tabelas de quantização (`quality="keep"`); MPO vira JPEG com a primeira
    imagem, em qualidade 95; WebP com qualidade 90.
    Arquivo já gravado no storage não é tocado. Quem salva sem validar (o
    admin e os formulários validam) leva `ValidationError` aqui, como no
    `upload_to`: nada é gravado com os metadados.
    """
    if not campo or getattr(campo, "_committed", True):
        return
    formato, pixels = _ler(campo)
    if formato not in FORMATOS:
        return  # recusado logo depois pelo `upload_to` (`_nome_gerado`)
    if pixels > PIXELS_MAXIMOS:
        raise ValidationError("A imagem tem resolução grande demais.", code="pixels")
    try:
        conteudo = _sem_metadados(campo, formato)
    except Exception:
        # Truncada, corrompida ou com metadado malformado que o `verify()` não
        # pega (ex.: struct.error do EXIF): recusa como formato, nunca 500 (G12).
        raise ValidationError("Envie uma imagem JPG, PNG ou WebP.", code="formato") from None
    campo.file = ContentFile(conteudo, name=campo.name)


def _sem_metadados(campo, formato):
    campo.seek(0)
    with Image.open(campo) as imagem:
        imagem.info.pop("comment", None)  # o Pillow regrava o comentário do JPEG
        orientacao = imagem.getexif().get(ORIENTACAO)
        if not (isinstance(orientacao, int) and 1 <= orientacao <= 8):
            orientacao = None  # valor fora do padrão EXIF (texto, 0, 99): descarta
        exif = Image.Exif()
        if orientacao:
            exif[ORIENTACAO] = orientacao
        opcoes = {"exif": exif.tobytes()} if orientacao else {}
        if imagem.info.get("icc_profile"):
            opcoes["icc_profile"] = imagem.info["icc_profile"]
        saida = io.BytesIO()
        if formato in ("JPEG", "MPO"):
            # MPO (foto de celular com várias imagens) não aceita "keep": vai a 1ª, em 95.
            imagem.save(saida, "JPEG", quality="keep" if formato == "JPEG" else 95, **opcoes)
        elif formato == "PNG":
            if "transparency" in imagem.info:
                opcoes["transparency"] = imagem.info["transparency"]
            opcoes.pop("exif", None)  # PNG sem EXIF: a orientação de PNG é rara
            imagem.save(saida, "PNG", **opcoes)
        else:
            imagem.save(saida, "WEBP", quality=90, **opcoes)
    return saida.getvalue()


def _nome_gerado(arquivo):
    extensao = FORMATOS.get(detectar_formato(arquivo))
    if extensao is None:
        # Só acontece se alguém salvar sem passar pela validação.
        raise ValidationError("Envie uma imagem JPG, PNG ou WebP.", code="formato")
    return f"projetos/{uuid.uuid4().hex}.{extensao}"


def caminho_capa(instance, filename):
    return _nome_gerado(instance.capa)


def caminho_imagem(instance, filename):
    return _nome_gerado(instance.arquivo)
