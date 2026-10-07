import pytest
from django.core.management import call_command


@pytest.fixture(scope="session", autouse=True)
def _tabela_de_cache(django_db_setup, django_db_blocker):
    """O rate limit usa o DatabaseCache; a tabela não nasce de migration (`createcachetable`)."""
    with django_db_blocker.unblock():
        call_command("createcachetable", verbosity=0)


@pytest.fixture(autouse=True)
def _midia_temporaria(settings, tmp_path):
    # Nunca o R2 de verdade: um `R2_BUCKET` no .env de quem roda os testes faria
    # os uploads e as remoções chegarem ao bucket.
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    }
    settings.MEDIA_ROOT = tmp_path
