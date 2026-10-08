"""Rotas raiz. Do coordenador — cada frente mexe só no urls.py do seu app."""

from django.conf import settings
from django.conf.urls.static import static
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

# Só no seu computador (DEBUG=1 e sem R2): serve as imagens enviadas de media/.
# Em produção o static() não devolve rota nenhuma (DEBUG=0) e as imagens vêm do R2.
if settings.DEBUG and settings.STORAGES["default"]["BACKEND"] == "django.core.files.storage.FileSystemStorage":
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
