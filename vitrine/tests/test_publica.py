"""Critérios de aceite "Vitrine pública" (specs/02-vitrine-publica.md) — guardrail 8."""

import re
from pathlib import Path
from datetime import date, datetime, timedelta, timezone as fuso

import pytest
from django.core.files.storage import FileSystemStorage
from django.utils import timezone
from django.template.loader import render_to_string
from django.urls import reverse

from cadastro.models import Curso, ImagemProjeto, Integrante, Projeto
from cadastro.tests import fabricas
from vitrine.tests import auxiliares as aux

ROTAS_DE_VOTO = ("/entrar", "/estacao", "/votar", "/votos", "/visitantes")


def publicado(**campos):
    if "edicao" not in campos:
        campos["edicao"] = aux.nova_edicao(data_evento=timezone.localdate() + timedelta(days=5))
    p, _ = aux.projeto_com_link(
        status=Projeto.Status.PUBLICADO,
        titulo="Agenda Escolar",
        resumo="Organiza as provas da turma.",
        descricao="Linha um.\nLinha dois.",
        link_demo="https://exemplo.com/demo",
        **campos,
    )
    Integrante.objects.create(projeto=p, nome="Ana", papel="Front-end", ordem=0)
    Integrante.objects.create(projeto=p, nome="Bruno", papel="", ordem=1)
    aux.com_capa(p)
    for i in range(2):
        ImagemProjeto.objects.create(projeto=p, arquivo=fabricas.imagem(), legenda=f"Tela {i}", ordem=i)
    return p


@pytest.mark.django_db
def test_projeto_publicado_mostra_o_conteudo(client):
    p = publicado()
    r = client.get(f"/projeto/{p.slug}/")
    assert r.status_code == 200
    html = r.content.decode()
    for esperado in ("Agenda Escolar", "Organiza as provas da turma.", "Linha um.", "Ana", "Front-end", "Bruno",
                     "https://exemplo.com/demo", p.turma.rotulo):
        assert esperado in html
    assert 'rel="noopener noreferrer nofollow"' in html


@pytest.mark.django_db
def test_galeria_mostra_as_imagens_com_a_legenda_como_alt(client):
    p = publicado()
    html = client.get(f"/projeto/{p.slug}/").content.decode()
    assert "Galeria" in html
    for imagem in p.imagens.all():
        assert f'src="{imagem.arquivo.url}"' in html
        assert f'alt="{imagem.legenda}"' in html
        assert f"<figcaption>{imagem.legenda}</figcaption>" in html


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["pre_cadastrado", "em_revisao", "ajustes"])
def test_slug_inexistente_e_projeto_nao_publicado_dao_o_mesmo_404(client, status):
    p, _ = aux.projeto_com_link(status=status, titulo="Escondido")
    nao_publicado = client.get(f"/projeto/{p.slug}/")
    inexistente = client.get("/projeto/nao-existe/")
    assert nao_publicado.status_code == inexistente.status_code == 404
    assert nao_publicado.content == inexistente.content
    assert "Escondido" not in nao_publicado.content.decode()


@pytest.mark.django_db
def test_meta_tags_open_graph_e_twitter_card(client, settings):
    p = publicado()
    html = client.get(f"/projeto/{p.slug}/").content.decode()
    assert '<meta property="og:title" content="Agenda Escolar">' in html
    assert '<meta property="og:description" content="Organiza as provas da turma.">' in html
    assert f'<meta property="og:url" content="{settings.URL_PUBLICA}/projeto/{p.slug}/">' in html
    assert '<meta name="twitter:card" content="summary_large_image">' in html
    imagem = re.search(r'<meta property="og:image" content="([^"]+)">', html).group(1)
    assert imagem.startswith(settings.URL_PUBLICA)
    assert p.capa.url.split("/")[-1] in imagem  # o arquivo original, não uma versão recortada


@pytest.mark.django_db
def test_og_usa_a_url_publica_e_nunca_o_host_da_requisicao(client, settings):
    settings.URL_PUBLICA = "https://vitrine.exemplo.com.br"
    settings.ALLOWED_HOSTS = ["*"]
    p = publicado()
    html = client.get(f"/projeto/{p.slug}/", HTTP_HOST="atacante.example").content.decode()
    assert f'content="https://vitrine.exemplo.com.br/projeto/{p.slug}/"' in html
    imagem = re.search(r'<meta property="og:image" content="([^"]+)">', html).group(1)
    assert imagem.startswith("https://vitrine.exemplo.com.br/")
    assert "atacante.example" not in html


class StorageRemoto(FileSystemStorage):
    """Simula o R2: a `url()` já vem absoluta, com o domínio do CDN."""

    def url(self, name):
        return f"https://cdn.exemplo.com.br/{name}"


@pytest.mark.django_db
def test_capa_com_url_absoluta_do_storage_nao_duplica_a_origem(client, settings):
    settings.STORAGES = {**settings.STORAGES, "default": {"BACKEND": f"{__name__}.StorageRemoto"}}
    p = publicado()
    html = client.get(f"/projeto/{p.slug}/").content.decode()
    imagem = re.search(r'<meta property="og:image" content="([^"]+)">', html).group(1)
    assert imagem.startswith("https://cdn.exemplo.com.br/projetos/")
    assert imagem.count("https://") == 1


@pytest.mark.django_db
def test_descricao_com_script_aparece_escapada(client):
    p = publicado()
    p.descricao = "<script>alert('xss')</script>"
    p.save(update_fields=["descricao", "atualizado_em"])
    html = client.get(f"/projeto/{p.slug}/").content.decode()
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


@pytest.mark.django_db
def test_titulo_e_resumo_com_aspas_e_tags_saem_escapados_nas_meta_e_no_title(client):
    p = publicado()
    p.titulo = 'A "B" <i>&'
    p.resumo = 'x" onload="alert(1)'
    p.save(update_fields=["titulo", "resumo", "atualizado_em"])
    html = client.get(f"/projeto/{p.slug}/").content.decode()
    assert '<meta property="og:title" content="A &quot;B&quot; &lt;i&gt;&amp;">' in html
    assert '<meta property="og:description" content="x&quot; onload=&quot;alert(1)">' in html
    assert "<title>A &quot;B&quot; &lt;i&gt;&amp; — Vitrine CPS</title>" in html
    assert 'onload="alert(1)"' not in html and "<i>" not in html


@pytest.mark.django_db
def test_nenhum_caminho_de_voto_na_vitrine_nem_no_partial(client):
    """Guardrail 8: nenhum link, formulário ou ação aponta para as rotas de voto."""
    p = publicado()
    paginas = [
        client.get(f"/projeto/{p.slug}/").content.decode(),
        client.get(reverse("vitrine:como_votar")).content.decode(),
        client.get("/projeto/nao-existe/").content.decode(),
        render_to_string("vitrine/_corpo_projeto.html", {"projeto": p}),
    ]
    for html in paginas:
        destinos = re.findall(r'(?:href|action|src)="([^"]*)"', html)
        for destino in destinos:
            assert not destino.startswith(ROTAS_DE_VOTO), destino
        assert "<form" not in html


@pytest.mark.django_db
def test_pagina_nao_traz_dados_do_representante_nem_token(client):
    p = publicado()
    token = p.regerar_link()
    html = client.get(f"/projeto/{p.slug}/").content.decode()
    assert token not in html and "/grupo/editar/" not in html
    assert p.representante_nome not in html
    assert p.ra_hmac not in html and aux.RA not in html
    assert (p.token_edicao_hash or "x") not in html


@pytest.mark.django_db
def test_projeto_de_edicao_antiga_continua_acessivel_com_o_nome_da_edicao_dele(client):
    p = publicado()
    edicao = p.turma.edicao
    edicao.ativa = False
    edicao.save()
    ativa = aux.nova_edicao()  # outra edição, com outro nome, agora é a ativa
    assert ativa.nome != edicao.nome
    r = client.get(f"/projeto/{p.slug}/")
    assert r.status_code == 200
    html = r.content.decode()
    assert edicao.nome in html and ativa.nome not in html


@pytest.mark.django_db
def test_convite_com_data_horario_e_endereco_sem_botao_de_voto(client):
    p = publicado()
    html = client.get(f"/projeto/{p.slug}/").content.decode()
    assert p.turma.edicao.data_evento.strftime("%d/%m/%Y") in html and "19h" in html
    assert "Fatec Olímpia" in html and "Adhemar Pereira de Barros" in html
    assert 'href="/como-votar/"' in html


@pytest.mark.django_db
def test_monograma_com_a_sigla_do_curso(client):
    p = publicado()
    html = client.get(f"/projeto/{p.slug}/").content.decode()
    assert f'class="monograma monograma--m" aria-hidden="true">{p.turma.curso.sigla[:3]}<' in html


@pytest.mark.django_db
def test_capa_aparece_como_banner_recortado(client):
    p = publicado()
    assert 'class="banner"' in client.get(f"/projeto/{p.slug}/").content.decode()


@pytest.mark.django_db
def test_pagina_404_tem_o_botao_conhecer_a_mostra(client):
    html = client.get("/projeto/nao-existe/").content.decode()
    assert "Conhecer a Mostra" in html and 'href="/como-votar/"' in html


@pytest.mark.django_db
def test_etec_so_mostra_o_primeiro_nome_como_gravado(client):
    p, _ = aux.projeto_com_link(status=Projeto.Status.PUBLICADO, unidade=Curso.Unidade.ETEC)
    Integrante.objects.create(projeto=p, nome="Carla", ordem=0)
    html = client.get(f"/projeto/{p.slug}/").content.decode()
    assert "Carla" in html


@pytest.mark.django_db
def test_depois_do_evento_o_convite_vira_registro_sem_botao_de_voto(client):
    edicao = aux.nova_edicao(data_evento=timezone.localdate() - timedelta(days=1))
    p = publicado(edicao=edicao)
    html = client.get(f"/projeto/{p.slug}/").content.decode()
    assert "participou da Mostra de Projetos realizada em" in html
    assert "Venha conhecer ao vivo" not in html and "19h" not in html
    assert "Quero votar" not in html and "/como-votar/" not in html


@pytest.mark.django_db
def test_no_dia_do_evento_o_convite_ainda_aparece(client):
    edicao = aux.nova_edicao(data_evento=timezone.localdate())
    p = publicado(edicao=edicao)
    assert "Venha conhecer ao vivo" in client.get(f"/projeto/{p.slug}/").content.decode()


def test_url_absoluta_nao_duplica_a_origem_do_storage_remoto(settings):
    from vitrine import servicos

    settings.URL_PUBLICA = "https://vitrine.exemplo.com.br"
    assert servicos.url_absoluta("https://cdn.exemplo.com.br/projetos/a.png") == "https://cdn.exemplo.com.br/projetos/a.png"
    assert servicos.url_absoluta("/media/projetos/a.png") == "https://vitrine.exemplo.com.br/media/projetos/a.png"
    assert servicos.url_absoluta("/projeto/x/") == "https://vitrine.exemplo.com.br/projeto/x/"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "agora_utc,convite",
    [
        (datetime(2026, 10, 30, 1, 0, tzinfo=fuso.utc), True),  # 22h de 29/10 em São Paulo: ainda é o dia do evento
        (datetime(2026, 10, 30, 2, 30, tzinfo=fuso.utc), True),  # 23h30 de 29/10 em São Paulo (UTC-3)
        (datetime(2026, 10, 30, 3, 0, tzinfo=fuso.utc), False),  # meia-noite de 30/10 em São Paulo: já passou
    ],
)
def test_convite_usa_a_data_local_e_nao_a_do_utc(client, monkeypatch, agora_utc, convite):
    edicao = aux.nova_edicao(data_evento=date(2026, 10, 29))
    p = publicado(edicao=edicao)
    monkeypatch.setattr(timezone, "now", lambda: agora_utc)
    html = client.get(f"/projeto/{p.slug}/").content.decode()
    assert ("Venha conhecer ao vivo" in html) is convite


@pytest.mark.django_db
def test_nenhuma_sintaxe_de_template_vaza_para_o_html(client):
    """Um comentário `{# #}` em várias linhas, por exemplo, seria impresso na página."""
    p = publicado()
    for caminho in (f"/projeto/{p.slug}/", "/projeto/nao-existe/", "/como-votar/", "/grupo/"):
        html = client.get(caminho).content.decode()
        for marca in ("{#", "#}", "{%", "%}", "{{", "}}"):
            assert marca not in html, (caminho, marca)


# --- Layout: capa em banner e página em 360 px (critério da spec) ------------------

# O CSS é o da identidade visual do projeto (static/css/base.css), ligado pelo base.html.
CSS = Path(__file__).resolve().parents[2] / "static" / "css" / "base.css"


def _lista_regras(css):
    """[(seletor, {propriedade: valor})] na ordem do arquivo, com seletor repetido
    aparecendo uma vez por ocorrência (o `body` do `@media print` não apaga o principal)."""
    css = re.sub(r"(?s)/\*.*?\*/", "", css)
    return [
        (
            " ".join(seletor.split()),
            dict((p.strip(), v.strip()) for p, v in (d.split(":", 1) for d in corpo.split(";") if ":" in d)),
        )
        for seletor, corpo in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
    ]


def _regras(css):
    """{seletor: {propriedade: valor}}, juntando as ocorrências de um mesmo seletor."""
    regras = {}
    for seletor, propriedades in _lista_regras(css):
        regras.setdefault(seletor, {}).update(propriedades)
    return regras


def _larguras_acima_de_360px(css):
    """(seletor, propriedade, valor) de toda largura fixa em px acima de 360, em toda
    ocorrência de cada seletor, e de todo `overflow-x` que força rolagem lateral."""
    achados = []
    for seletor, propriedades in _lista_regras(css):
        for nome in ("width", "min-width"):
            pixels = re.fullmatch(r"(\d+(?:\.\d+)?)px", propriedades.get(nome, ""))
            if pixels and float(pixels.group(1)) > 360:
                achados.append((seletor, nome, propriedades[nome]))
        if propriedades.get("overflow-x") == "scroll":
            achados.append((seletor, "overflow-x", "scroll"))
    return achados


def test_css_da_capa_em_banner_recortado():
    regras = _regras(CSS.read_text(encoding="utf-8"))
    banner = regras[".banner"]
    assert banner["object-fit"] == "cover" and banner["width"] == "100%"
    assert "aspect-ratio" in banner
    assert regras["img"]["max-width"] == "100%"


def test_css_nao_tem_largura_fixa_maior_que_a_tela_de_360px():
    assert _larguras_acima_de_360px(CSS.read_text(encoding="utf-8")) == []


def test_largura_em_seletor_repetido_tambem_e_checada():
    # O `body` repetido (como o do `@media print` no base.css) não esconde o primeiro.
    css = "body { min-width: 480px; }\n@media print { body { background: #fff; } }\n.x { overflow-x: scroll; }"
    assert _larguras_acima_de_360px(css) == [("body", "min-width", "480px"), (".x", "overflow-x", "scroll")]


@pytest.mark.django_db
def test_pagina_publica_liga_o_base_css_e_nao_tem_largura_fixa_no_html(client):
    p = publicado()
    for url in (f"/projeto/{p.slug}/", "/projeto/nao-existe/"):
        html = client.get(url).content.decode()
        assert 'rel="stylesheet"' in html and "css/base.css" in html
        assert "vitrine/vitrine.css" not in html
        assert 'name="viewport" content="width=device-width, initial-scale=1"' in html
        # Sem `width="…"`/`style="width:…px"` fixos acima de 360 px nos elementos.
        for largura in re.findall(r'\swidth="(\d+)"', html):
            assert int(largura) <= 360
        for largura in re.findall(r"width:\s*(\d+)px", html):
            assert int(largura) <= 360
