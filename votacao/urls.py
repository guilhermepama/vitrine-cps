# Rotas da frente votacao. Já incluídas em config/urls.py — a frente só
# mexe aqui, nunca no urls.py raiz.
from django.urls import path

from votacao import views_visitante

app_name = "votacao"

urlpatterns = [
    path("visitantes", views_visitante.visitantes, name="visitantes"),
]
