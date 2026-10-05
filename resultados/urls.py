# Rotas da frente resultados (spec 04). Já incluídas em config/urls.py com o
# prefixo "resultados/"; a frente só mexe aqui, nunca no urls.py raiz.
from django.urls import path

from resultados import views

app_name = "resultados"

urlpatterns = [
    path("<int:edicao_id>/", views.ranking, name="ranking"),
    path("<int:edicao_id>/operacional/", views.operacional, name="operacional"),
    path("<int:edicao_id>/visitantes.csv", views.visitantes_csv, name="visitantes_csv"),
]
