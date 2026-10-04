"""Cache compartilhado do rate limit (guardrail 7, specs 02 e 03).

O `DatabaseCache` com o padrão do Django (MAX_ENTRIES=300) apaga ~1/3 das
chaves vivas em ordem alfabética quando a tabela passa de 300 linhas: os
contadores do rate limit somem e quem estava barrado volta a passar
(parecer do PR #34).
"""

import pytest
from django.core.cache import caches


@pytest.mark.django_db
def test_chaves_vivas_sobrevivem_acima_de_300_linhas():
    cache = caches["default"]
    for i in range(400):
        cache.set(f"teste:{i:03d}", i, 600)
    sumidas = [i for i in range(400) if cache.get(f"teste:{i:03d}") != i]
    assert sumidas == []
