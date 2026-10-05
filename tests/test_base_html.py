"""`templates/base.html` do projeto (spec 02, "Dependências do coordenador").

As páginas das specs herdam este arquivo pelos blocos `titulo`, `meta` e
`conteudo`. A identidade visual entra depois sem mudar o nome nem os blocos.
"""

from django.template import engines

FILHO = (
    '{% extends "base.html" %}'
    "{% block titulo %}Projeto X — Vitrine CPS{% endblock %}"
    '{% block meta %}<meta property="og:title" content="Projeto X">{% endblock %}'
    "{% block conteudo %}<p>corpo</p>{% endblock %}"
)


def test_blocos_titulo_meta_e_conteudo():
    html = engines["django"].from_string(FILHO).render()
    assert "<title>Projeto X — Vitrine CPS</title>" in html
    assert '<meta property="og:title" content="Projeto X">' in html
    assert "<p>corpo</p>" in html
    assert '<html lang="pt-BR">' in html
    assert 'name="viewport"' in html


def test_titulo_padrao():
    html = engines["django"].from_string('{% extends "base.html" %}').render()
    assert "<title>Vitrine CPS</title>" in html
