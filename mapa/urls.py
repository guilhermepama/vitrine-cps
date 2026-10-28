# Rotas do mapa do evento. Incluídas em config/urls.py sob /mapa/.
from django.urls import path

from mapa import views

app_name = "mapa"

urlpatterns = [
    path("", views.mapa, name="mapa"),
]
