import pytest


@pytest.fixture(autouse=True)
def _estaticos_sem_manifesto(settings):
    """Nos testes não há `collectstatic`, então o manifesto do whitenoise não
    existe e qualquer template com {% static %} quebraria. Usa o storage
    simples só durante os testes."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
