"""Views da vitrine pública e da área do grupo (spec 02).

As rotas ficam em vitrine/urls.py, nunca no urls.py raiz. Nenhuma view daqui
leva a /entrar, /estacao, /votar, /votos ou /visitantes (guardrail 8).
"""

from functools import wraps

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseNotFound
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from cadastro.models import ImagemProjeto
from vitrine import servicos
from vitrine.forms import ImagemUploadForm, ProjetoGrupoForm, integrante_formset


def paginas_do_grupo(view):
    """Páginas do grupo: sem cache, sem indexação, sem referência (G11 por analogia)."""

    @wraps(view)
    @never_cache
    def envolvida(request, *args, **kwargs):
        resposta = view(request, *args, **kwargs)
        resposta["Referrer-Policy"] = "no-referrer"
        resposta["X-Robots-Tag"] = "noindex"
        return resposta

    return envolvida


def como_votar(request):
    return render(request, "vitrine/como_votar.html")


# --- Reivindicação pelo RA ----------------------------------------------------


@paginas_do_grupo
@require_http_methods(["GET", "POST"])
def grupo(request):
    if request.method == "GET":
        return render(request, "vitrine/grupo_reivindicar.html")
    if servicos.limite_estourado(request):
        return render(request, "vitrine/grupo_limite.html", status=429)
    # O RA só passa daqui para hash_ra: nunca é gravado, logado nem devolvido.
    token = servicos.reivindicar(request.POST.get("ra", "")[:60])
    if token is None:
        servicos.registrar_falha(request)
        return render(request, "vitrine/grupo_reivindicar.html", {"recusado": True}, status=400)
    link = servicos.url_absoluta(reverse("vitrine:editar", args=[token]))
    return render(request, "vitrine/grupo_link.html", {"link": link})


# --- Edição pelo link ---------------------------------------------------------


def _link_invalido(request):
    return render(request, "vitrine/link_invalido.html", status=404)


def _403_com_estado_atual(request, token):
    """Recarrega o projeto: o que o POST leu antes da trava pode estar velho (corrida)."""
    projeto = servicos.projeto_do_token(token)
    if projeto is None:  # o link foi substituído no meio do envio
        return _link_invalido(request)
    return _tela_de_edicao(request, projeto, token, status=403)


def _tela_de_edicao(request, projeto, token, form=None, formset=None, pendencias=None, erro_imagem=None, status=200):
    motivo = servicos.motivo_somente_leitura(projeto)
    contexto = {
        "projeto": projeto,
        "token": token,
        "motivo_somente_leitura": motivo,
        "pendencias": projeto.pendencias_para_publicar() if pendencias is None else pendencias,
        "erro_imagem": erro_imagem,
        "etec": projeto.turma.curso.unidade == "etec",
        "imagens": projeto.imagens.all(),
        "maximo_imagens": ImagemProjeto.MAXIMO_POR_PROJETO,
        "integrantes": projeto.integrantes.all(),
    }
    if motivo is None:
        contexto["form"] = form or ProjetoGrupoForm(instance=projeto)
        contexto["formset"] = formset or integrante_formset(projeto)
        contexto["pode_enviar"] = not contexto["pendencias"]
    return render(request, "vitrine/editar.html", contexto, status=status)


@paginas_do_grupo
@require_http_methods(["GET", "POST"])
def editar(request, token):
    projeto = servicos.projeto_do_token(token)
    if projeto is None:
        return _link_invalido(request)
    if request.method == "GET":
        return _tela_de_edicao(request, projeto, token)

    if not servicos.pode_editar(projeto):
        return _tela_de_edicao(request, projeto, token, status=403)
    acao = request.POST.get("acao")
    if acao not in ("salvar", "enviar"):
        return _tela_de_edicao(request, projeto, token, status=400)

    form = formset = None
    try:
        with transaction.atomic():
            travado = servicos.travar_para_edicao(projeto.pk, token)
            form = ProjetoGrupoForm(request.POST, instance=travado)
            formset = integrante_formset(travado, data=request.POST)
            if not (form.is_valid() and formset.is_valid()):
                transaction.set_rollback(True)
            else:
                # Só os campos que o grupo edita (a spec proíbe regravar a linha inteira).
                travado = form.save(commit=False)
                travado.save(update_fields=[*ProjetoGrupoForm.Meta.fields, "atualizado_em"])
                formset.save()
                if acao == "enviar":
                    servicos.enviar_para_revisao(travado)
    except (servicos.EdicaoEncerrada, ValidationError):
        # ValidationError: as travas da spec 01 vivem no save() (a votação abriu no meio do envio).
        return _403_com_estado_atual(request, token)
    except servicos.PendenciasParaEnviar as erro:
        # A transação foi desfeita: remonta os formulários só com o que o grupo
        # digitou (os objetos antigos já carregam ids de linhas que não existem).
        digitado = ProjetoGrupoForm(request.POST, instance=projeto)
        integrantes = integrante_formset(projeto, data=request.POST)
        return _tela_de_edicao(request, projeto, token, digitado, integrantes, pendencias=erro.pendencias, status=400)

    if not (form.is_valid() and formset.is_valid()):
        return _tela_de_edicao(request, projeto, token, form, formset, status=400)

    messages.success(request, "Enviado para revisão da coordenação." if acao == "enviar" else "Rascunho salvo.")
    return redirect("vitrine:editar", token=token)


# --- Imagens, uma por requisição ----------------------------------------------


@paginas_do_grupo
@require_POST
def imagem(request, token):
    projeto = servicos.projeto_do_token(token)
    if projeto is None:
        return _link_invalido(request)
    # Quem não pode editar leva 403 antes de qualquer leitura do arquivo.
    if not servicos.pode_editar(projeto):
        return _tela_de_edicao(request, projeto, token, status=403)
    # Nenhuma requisição leva mais de uma imagem.
    if sum(len(arquivos) for _, arquivos in request.FILES.lists()) != 1:
        return _tela_de_edicao(request, projeto, token, erro_imagem="Envie uma imagem por vez.", status=400)
    form = ImagemUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        mensagem = " ".join(m for erros in form.errors.values() for m in erros)
        return _tela_de_edicao(request, projeto, token, erro_imagem=mensagem, status=400)
    dados = form.cleaned_data
    try:
        servicos.enviar_imagem(projeto.pk, token, dados["tipo"], dados["arquivo"], dados["legenda"])
    except servicos.EdicaoEncerrada:
        return _403_com_estado_atual(request, token)
    except ValidationError as erro:
        if erro.code in ("formato", "pixels"):  # a imagem foi recusada ao ser regravada
            return _tela_de_edicao(request, projeto, token, erro_imagem=" ".join(erro.messages), status=400)
        return _403_com_estado_atual(request, token)
    except servicos.LimiteDeImagens:
        return _tela_de_edicao(
            request,
            projeto,
            token,
            erro_imagem=f"O projeto já tem o máximo de {ImagemProjeto.MAXIMO_POR_PROJETO} imagens na galeria.",
            status=400,
        )
    messages.success(request, "Imagem enviada.")
    return redirect("vitrine:editar", token=token)


@paginas_do_grupo
@require_POST
def imagem_remover(request, token, imagem_id):
    projeto = servicos.projeto_do_token(token)
    if projeto is None:
        return _link_invalido(request)
    try:
        servicos.remover_imagem(projeto.pk, token, imagem_id)
    except servicos.EdicaoEncerrada:
        return _403_com_estado_atual(request, token)
    except servicos.ImagemInexistente:
        return HttpResponseNotFound("Imagem não encontrada.")
    messages.success(request, "Imagem removida.")
    return redirect("vitrine:editar", token=token)
