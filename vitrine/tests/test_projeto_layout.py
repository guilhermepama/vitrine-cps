"""Layout da página do projeto (spec 07). O comportamento é da spec 02 (test_publica.py)."""

import pytest

from vitrine.templatetags.vitrine_extras import dominio
from vitrine.tests.test_publica import publicado


@pytest.mark.parametrize(
    ("url", "esperado"),
    [
        ("https://www.github.com/grupo/repo", "github.com"),
        ("https://youtu.be/abc", "youtu.be"),
        ("https://exemplo.com/demo?x=1", "exemplo.com"),
        ("", ""),
        (None, ""),
    ],
)
def test_dominio(url, esperado):
    assert dominio(url) == esperado


@pytest.mark.django_db
def test_links_do_projeto_mostram_o_dominio(client):
    p = publicado()
    html = client.get(f"/projeto/{p.slug}/").content.decode()
    assert 'Demonstração <span class="mono">exemplo.com</span>' in html


@pytest.mark.django_db
def test_menu_leva_aos_projetos_e_a_area_do_grupo(client):
    p = publicado()
    html = client.get(f"/projeto/{p.slug}/").content.decode()
    assert 'href="/projetos/"' in html and 'href="/grupo/" class="nav__botao"' in html
    assert "js/menu.js" in html


@pytest.mark.django_db
def test_sem_secao_de_impacto_nesta_edicao(client):
    p = publicado()
    html = client.get(f"/projeto/{p.slug}/").content.decode()
    assert "Impacto" not in html
    assert "01 — Sobre o projeto" in html and "02 — Galeria" in html and "03 — Equipe" in html
