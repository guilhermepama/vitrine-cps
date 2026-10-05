# Rotas da frente votacao. Já incluídas em config/urls.py — a frente só
# mexe aqui, nunca no urls.py raiz.
from django.urls import path

from votacao import views_entrar, views_estacao, views_visitante, views_voto

app_name = "votacao"

urlpatterns = [
    path("estacao/<int:estacao_id>", views_estacao.estacao, name="estacao"),
    path("estacao/<int:estacao_id>/qr", views_estacao.estacao_qr, name="estacao_qr"),
    path("entrar", views_entrar.entrar, name="entrar"),
    path("visitantes", views_visitante.visitantes, name="visitantes"),
    path("votar", views_voto.votar, name="votar"),
    path("votos", views_voto.votos, name="votos"),
]
