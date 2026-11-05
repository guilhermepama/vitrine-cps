"""Página pública do resultado da Conexão Fatec (spec 09).

Diferente do resto do app (rotas só de admin, spec 04), esta página é pública e
estática: cada edição divulgada tem o seu template em
`resultados/templates/resultados/publico/<ano>.html`, um retrato do resultado oficial
aprovado pela coordenação. Ela não consulta o banco — o ranking divulgado não muda
se alguém editar uma nota depois — e não tem nenhum caminho de voto (G8).
"""

from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET

# Edições com resultado divulgado: ano → template. Ano fora daqui → 404 (G12).
DIVULGADOS = {
    2026: "resultados/publico/2026.html",
}


@require_GET
def resultado(request, ano):
    template = DIVULGADOS.get(ano)
    if template is None:
        raise Http404("Resultado não divulgado")
    return render(request, template)
