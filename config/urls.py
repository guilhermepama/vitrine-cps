"""Rotas raiz. Do coordenador — cada frente mexe só no urls.py do seu app."""

from django.contrib import admin
from django.urls import include, path

from config.views import saude

admin.site.site_header = "Vitrine CPS — administração"
admin.site.site_title = "Vitrine CPS"
admin.site.index_title = "Painel"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("saude/", saude, name="saude"),
    # Frentes com páginas públicas. As rotas de cada uma moram no app.
    path("", include("vitrine.urls")),
    path("", include("votacao.urls")),
    path("resultados/", include("resultados.urls")),
]
