"""Formulários da área do grupo (spec 02)."""

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from cadastro.imagens import validar_imagem
from cadastro.models import Integrante, Projeto, somente_https
from vitrine.servicos import TIPO_CAPA, TIPO_EXTRA


def _campo_url(rotulo):
    return forms.URLField(
        label=rotulo,
        required=False,
        max_length=200,
        assume_scheme="https",
        validators=[somente_https],
        help_text="Opcional. Só endereços https://",
    )


class ProjetoGrupoForm(forms.ModelForm):
    """O que o grupo edita. O título não entra: vem da lista das coordenações."""

    link_repositorio = _campo_url("Repositório")
    link_demo = _campo_url("Demonstração")
    link_video = _campo_url("Vídeo")

    class Meta:
        model = Projeto
        fields = ["resumo", "descricao", "componente_origem", "link_repositorio", "link_demo", "link_video"]
        labels = {
            "resumo": "Resumo (até 280 caracteres — aparece na prévia do WhatsApp)",
            "descricao": "Descrição (até 3.000 caracteres)",
            "componente_origem": "Componente de origem (opcional, ex.: PI II — Eventos)",
        }
        widgets = {
            "resumo": forms.Textarea(attrs={"rows": 3, "maxlength": 280}),
            "descricao": forms.Textarea(attrs={"rows": 10, "maxlength": 3000}),
        }


class IntegranteFormSetBase(BaseInlineFormSet):
    default_error_messages = {
        **BaseInlineFormSet.default_error_messages,
        "too_many_forms": "Informe no máximo %(num)d integrantes.",
    }

    def save_new(self, form, commit=True):
        form.instance.ordem = self.forms.index(form)
        return super().save_new(form, commit=commit)

    def save_existing(self, form, obj, commit=True):
        form.instance.ordem = self.forms.index(form)
        return super().save_existing(form, obj, commit=commit)


def integrante_formset(projeto, **kwargs):
    """Mostra os integrantes atuais mais até 3 linhas em branco (sem passar de 10).

    Sem JavaScript, mais linhas vêm a cada salvamento.
    """
    maximo = Integrante.MAXIMO_POR_PROJETO
    extras = max(0, min(3, maximo - projeto.integrantes.count()))
    classe = inlineformset_factory(
        Projeto,
        Integrante,
        formset=IntegranteFormSetBase,
        fields=["nome", "papel"],
        extra=extras,
        max_num=maximo,
        absolute_max=maximo,
        validate_max=True,
        can_delete=True,
    )
    return classe(instance=projeto, **kwargs)


class ImagemUploadForm(forms.Form):
    tipo = forms.ChoiceField(
        choices=[(TIPO_CAPA, "Capa"), (TIPO_EXTRA, "Imagem da galeria")],
        error_messages={"invalid_choice": "Tipo de imagem inválido.", "required": "Tipo de imagem inválido."},
    )
    arquivo = forms.ImageField(
        validators=[validar_imagem],
        error_messages={"invalid_image": "Envie uma imagem JPG, PNG ou WebP.", "required": "Escolha uma imagem."},
    )
    legenda = forms.CharField(max_length=120, required=False)
