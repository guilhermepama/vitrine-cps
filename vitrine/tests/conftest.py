import pytest
from django.core.management import call_command


@pytest.fixture(scope="session", autouse=True)
def _tabela_de_cache(django_db_setup, django_db_blocker):
    """O rate limit usa o DatabaseCache; a tabela não nasce de migration (`createcachetable`)."""
    with django_db_blocker.unblock():
        call_command("createcachetable", verbosity=0)


@pytest.fixture(autouse=True)
def _midia_temporaria(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
