"""URLconf de teste: igual ao do projeto, mas `vitrine:como_votar` mora em
/ajuda/como-votar/. Prova que a cédula redireciona pela rota NOMEADA."""

from django.urls import include, path

from config.urls import urlpatterns as urlpatterns_projeto
from vitrine import urls as vitrine_urls
from vitrine import views

# Rotas do vitrine iguais às reais, só com `como_votar` em outro caminho.
_vitrine = [
    path("ajuda/como-votar/", views.como_votar, name="como_votar")
    if p.name == "como_votar"
    else p
    for p in vitrine_urls.urlpatterns
]

# Tudo do projeto, menos o include original do vitrine.
urlpatterns = [
    p for p in urlpatterns_projeto if getattr(p, "urlconf_name", None) is not vitrine_urls
] + [path("", include((_vitrine, "vitrine")))]
