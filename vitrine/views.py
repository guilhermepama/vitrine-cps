"""Views da vitrine pública e da área do grupo (spec 02).

As rotas ficam em vitrine/urls.py, nunca no urls.py raiz. Nenhuma view daqui
leva a /entrar, /estacao, /votar, /votos ou /visitantes (guardrail 8).
"""

from functools import wraps

from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from vitrine import servicos


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


@paginas_do_grupo
def editar(request, token):
    # A tela de edição chega na fatia seguinte; até lá o link ainda não abre
    # nada. A rota existe agora para a reivindicação gerar o link com reverse().
    return render(request, "vitrine/link_invalido.html", status=404)
