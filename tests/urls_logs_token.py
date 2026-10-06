"""URLconf só dos testes do filtro de log do link de edição.

Os testes de `test_logs_token_edicao.py` precisam de um 404 em
`/grupo/editar/<token>/...` e em outra rota. Com as rotas reais, o resultado
depende do app `vitrine`: a rota de imagem é só POST (GET vira 405) e a
página pública consulta o banco. Aqui as duas views levantam `Http404` sem
tocar no banco, e o teste mede só o filtro.
"""

from django.http import Http404
from django.urls import path


def _nao_encontrado(request, **kwargs):
    raise Http404


urlpatterns = [
    path("grupo/editar/<str:token>/imagem/", _nao_encontrado),
    path("projeto/<slug:slug>/", _nao_encontrado),
]
