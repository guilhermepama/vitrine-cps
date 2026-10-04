"""Respostas genéricas das rotas do visitante (spec 03, guardrail 5)."""

from django.http import HttpResponseBadRequest
from django.template.loader import render_to_string


def qr_expirado():
    """Página "QR expirado", 400, corpo sempre idêntico.

    Renderizada sem `request`: sem token CSRF nem nada variável no corpo
    (armadilha A6 do plano). A F4 usa a mesma em `/entrar`.
    """
    return HttpResponseBadRequest(render_to_string("votacao/qr_expirado.html"))
