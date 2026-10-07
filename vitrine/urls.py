# Rotas da frente vitrine. Já incluídas em config/urls.py — a frente só
# mexe aqui, nunca no urls.py raiz.
from django.urls import path

from vitrine import views

app_name = "vitrine"

urlpatterns = [
    path("como-votar/", views.como_votar, name="como_votar"),
    path("grupo/", views.grupo, name="grupo"),
    path("grupo/editar/<str:token>/", views.editar, name="editar"),
]
