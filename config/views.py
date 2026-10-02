from django.db import DatabaseError, connection
from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@never_cache
@require_GET
def saude(request):
    """Verificação de saúde para a plataforma e o monitor de disponibilidade.

    Toca o banco: no dia do evento, o monitor chamando esta rota mantém
    aplicação e Neon acordados. Resposta sem detalhe do erro.
    """
    try:
        connection.ensure_connection()
        ok = connection.is_usable()
    except DatabaseError:
        ok = False
    if ok:
        return HttpResponse("ok", content_type="text/plain")
    return HttpResponse("indisponivel", status=503, content_type="text/plain")
