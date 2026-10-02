"""Validação e nome de arquivo das imagens dos projetos (guardrail 14)."""

import uuid

from django.core.exceptions import ValidationError
from PIL import Image

TAMANHO_MAXIMO = 3 * 1024 * 1024  # 3 MB
# MPO = JPEG com várias imagens, como muitos celulares salvam a foto: vira .jpg.
FORMATOS = {"JPEG": "jpg", "MPO": "jpg", "PNG": "png", "WEBP": "webp"}


def detectar_formato(arquivo):
    """Formato real do arquivo, lido do conteúdo (não da extensão nem do content_type)."""
    try:
        arquivo.seek(0)
        with Image.open(arquivo) as imagem:
            formato = imagem.format
            imagem.verify()
    except Exception:
        return None
    finally:
        arquivo.seek(0)
    return formato


def validar_imagem(arquivo):
    if arquivo.size > TAMANHO_MAXIMO:
        raise ValidationError("A imagem pode ter no máximo 3 MB.", code="tamanho")
    if detectar_formato(arquivo) not in FORMATOS:
        raise ValidationError("Envie uma imagem JPG, PNG ou WebP.", code="formato")


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
