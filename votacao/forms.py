"""Formulário do visitante (spec 03, "Validação de entrada" — guardrails 9 e 12).

Só nome, email, telefone e consentimento. Campos além desses são ignorados.
Tamanhos contados depois de remover só o espaço ASCII das pontas, como na
F3: tab, quebra de linha e outros brancos não são removidos (no nome, são
caractere de controle e a matriz recusa).
"""

import re
import unicodedata

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator

TELEFONE_PERMITIDO = re.compile(r"[0-9 ()+-]*")


class TextoSemEspacoNasPontas(forms.CharField):
    def __init__(self, **kwargs):
        super().__init__(strip=False, **kwargs)

    def to_python(self, value):
        # Antes de required e dos validadores de tamanho, que medem o resultado.
        return super().to_python(value).strip(" ")


def _sem_caractere_de_controle(valor):
    # Categoria Unicode Cc: C0 (\x00–\x1f, inclui \t e \n), DEL e C1.
    if any(unicodedata.category(c) == "Cc" for c in valor):
        raise ValidationError("inválido")


def _digitos_do_telefone(valor):
    if not TELEFONE_PERMITIDO.fullmatch(valor):
        raise ValidationError("inválido")
    digitos = re.sub(r"[^0-9]", "", valor)
    if len(digitos) in (10, 11) or (len(digitos) in (12, 13) and digitos.startswith("55")):
        return digitos
    raise ValidationError("inválido")


class VisitanteForm(forms.Form):
    nome = TextoSemEspacoNasPontas(min_length=2, max_length=120, validators=[_sem_caractere_de_controle])
    email = TextoSemEspacoNasPontas(max_length=254, validators=[EmailValidator()])
    telefone = TextoSemEspacoNasPontas(required=False, max_length=20)
    consentimento = forms.BooleanField(required=True)

    def clean_consentimento(self):
        # Lista de aceitos: o checkbox do template não tem value, então o
        # navegador manda "on". Qualquer outro texto ("0", "off", "true"...)
        # não é aceite explícito (guardrail 10).
        if self.data.get("consentimento") != "on":
            raise ValidationError("inválido")
        return True

    def clean_telefone(self):
        valor = self.cleaned_data["telefone"]
        # Gravado só com os dígitos; vazio vira NULL.
        return _digitos_do_telefone(valor) if valor else None
