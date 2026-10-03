"""Página da estação e renovação do QR (spec 03, "Acesso à página da estação").

Só para staff ativo com `votacao.operar_estacao`. A autenticação vem antes de
buscar a estação, para não revelar quais ids existem: anônimo vai para o
login do admin; logado sem staff ou sem a permissão recebe o mesmo 404 da
estação inexistente.
"""

from urllib.parse import urlencode

import qrcode
from django.contrib.auth.views import redirect_to_login
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from qrcode.image.svg import SvgPathImage

from votacao.assinatura import ROTACAO_QR, nova_janela
from votacao.models import Estacao

# Rota da emissão (F4). Caminho fixo: é o que a spec define para o QR.
ROTA_ENTRAR = "/entrar"


def _estacao_autorizada(request, estacao_id):
    """Estação ativa ou Http404. Devolve None para anônimo (vai para o login)."""
    usuario = request.user
    if not usuario.is_authenticated:
        return None
    if not (usuario.is_active and usuario.is_staff and usuario.has_perm("votacao.operar_estacao")):
        raise Http404
    estacao = Estacao.objects.filter(pk=estacao_id, ativa=True).first()
    if estacao is None:
        raise Http404
    return estacao


def _login(request):
    # Login do admin: não depende de LOGIN_URL no settings.py. O next é sempre
    # a página da estação, mesmo quando quem caiu foi a renovação do QR.
    proxima = reverse("votacao:estacao", args=[request.resolver_match.kwargs["estacao_id"]])
    return redirect_to_login(proxima, reverse("admin:login"))


def svg_do_qr(url):
    return qrcode.make(url, image_factory=SvgPathImage).to_string(encoding="unicode")


def _svg_da_estacao(request, estacao):
    url = request.build_absolute_uri(ROTA_ENTRAR) + "?" + urlencode(nova_janela(estacao.pk), safe=":")
    return svg_do_qr(url)


@require_GET
@never_cache
def estacao(request, estacao_id):
    estacao_ = _estacao_autorizada(request, estacao_id)
    if estacao_ is None:
        return _login(request)
    contexto = {
        "estacao": estacao_,
        # SVG gerado aqui pela biblioteca qrcode a partir da nossa URL.
        "qr_svg": mark_safe(_svg_da_estacao(request, estacao_)),
        "rotacao": ROTACAO_QR,
    }
    return render(request, "votacao/estacao.html", contexto)


@require_GET
@never_cache
def estacao_qr(request, estacao_id):
    """Só o SVG do QR novo, para o fetch da página trocar a imagem sem recarregar."""
    estacao_ = _estacao_autorizada(request, estacao_id)
    if estacao_ is None:
        return _login(request)
    return HttpResponse(_svg_da_estacao(request, estacao_), content_type="image/svg+xml; charset=utf-8")
