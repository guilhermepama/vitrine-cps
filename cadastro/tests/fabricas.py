"""Dados fictícios para os testes do cadastro."""

import io
from datetime import date, timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from cadastro.models import Curso, Edicao, Projeto, Turma
from cadastro.seguranca import hash_ra


def edicao(**campos):
    padrao = {
        "nome": "2026/2",
        "data_evento": date(2026, 10, 29),
        "prazo_edicao": timezone.now() + timedelta(days=7),
    }
    padrao.update(campos)
    return Edicao.objects.create(**padrao)


def curso(sigla="DSM", unidade=Curso.Unidade.FATEC):
    return Curso.objects.create(sigla=sigla, nome=f"Curso {sigla}", unidade=unidade)


def turma(edicao_=None, curso_=None, **campos):
    padrao = {"numero_periodo": 3, "tipo_periodo": Turma.TipoPeriodo.SEMESTRE}
    padrao.update(campos)
    return Turma.objects.create(edicao=edicao_ or edicao(), curso=curso_ or curso(), **padrao)


def projeto(turma_=None, titulo="Agenda Escolar", **campos):
    padrao = {"representante_nome": "Maria Teste", "ra_hmac": hash_ra("1234567890123")}
    padrao.update(campos)
    return Projeto.objects.create(turma=turma_ or turma(), titulo=titulo, **padrao)


def imagem(formato="PNG", nome="foto.png", tamanho=(20, 20)):
    buffer = io.BytesIO()
    Image.new("RGB", tamanho, "red").save(buffer, format=formato)
    return SimpleUploadedFile(nome, buffer.getvalue(), content_type="image/png")
