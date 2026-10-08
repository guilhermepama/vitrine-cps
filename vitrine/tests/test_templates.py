"""Nenhuma tela mostra sintaxe de template, chave solta ou valor vazio impresso (specs/02-vitrine-publica.md).

Um comentário `{# #}` em várias linhas, por exemplo, não é comentário: o Django o imprime
na página. Este arquivo olha os arquivos e renderiza cada tela em cada estado.
"""

import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.cache import cache
from django.utils import timezone

from cadastro.models import Integrante, ImagemProjeto, Projeto
from cadastro.tests import fabricas
from vitrine import servicos
from vitrine.tests import auxiliares as aux

PASTA_DOS_TEMPLATES = Path(__file__).resolve().parent.parent / "templates" / "vitrine"
SINTAXE = ("{#", "#}", "{%", "%}", "{{", "}}")


def test_nenhum_template_tem_comentario_de_uma_linha_quebrado():
    """`{# ... #}` só funciona numa linha; em várias linhas use `{% comment %}`."""
    arquivos = list(PASTA_DOS_TEMPLATES.glob("*.html"))
    assert arquivos
    for arquivo in arquivos:
        for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
            assert not ("{#" in linha and "#}" not in linha), f"{arquivo.name}:{numero} comentário {{# sem #}}"
            assert not ("#}" in linha and "{#" not in linha), f"{arquivo.name}:{numero} #}} solto"
            assert linha.count("{{") == linha.count("}}"), f"{arquivo.name}:{numero} {{{{ }}}} desbalanceado"
            assert linha.count("{%") == linha.count("%}"), f"{arquivo.name}:{numero} {{% %}} desbalanceado"


def _sem_script_nem_estilo(html):
    return re.sub(r"(?is)<(script|style)\b.*?</\1>", "", html)


def _texto_visivel(html):
    """Só o texto da página: sem script, estilo, tags nem atributos."""
    return re.sub(r"(?s)<[^>]*>", "", _sem_script_nem_estilo(html))


def _confere(html, onde):
    codigo = _sem_script_nem_estilo(html)
    for marca in SINTAXE:
        assert marca not in codigo, (onde, marca)
    # Chave solta no HTML costuma ser sintaxe de template ou dict impresso.
    assert "{" not in codigo and "}" not in codigo, (onde, "chave solta")
    for lixo in ("<function", "<django", "Traceback", "object at 0x"):
        assert lixo not in codigo, (onde, lixo)
    texto = _texto_visivel(html)
    for lixo in ("None", "[]"):
        assert lixo not in texto, (onde, lixo)


def _projeto_completo(status=Projeto.Status.PRE_CADASTRADO, **campos):
    p, token = aux.projeto_com_link(
        status=status, resumo="Resumo.", descricao="Linha um.\nLinha dois.", link_demo="https://exemplo.com/d", **campos
    )
    Integrante.objects.create(projeto=p, nome="Ana", papel="Front-end", ordem=0)
    Integrante.objects.create(projeto=p, nome="Bruno", papel="", ordem=1)
    aux.com_capa(p)
    ImagemProjeto.objects.create(projeto=p, arquivo=fabricas.imagem(), legenda="Tela", ordem=0)
    ImagemProjeto.objects.create(projeto=p, arquivo=fabricas.imagem(), legenda="", ordem=1)
    return p, token


@pytest.mark.django_db
def test_telas_publicas_e_de_reivindicacao_em_todos_os_estados(client):
    publicado, _ = _projeto_completo(status=Projeto.Status.PUBLICADO)
    passado = aux.nova_edicao(ativa=False, data_evento=timezone.localdate() - timedelta(days=3))
    antigo, _ = aux.projeto_com_link(status=Projeto.Status.PUBLICADO, edicao=passado, ra_hmac=aux.hash_ra("7654321"))
    aux.projeto_reivindicavel(ra="2026001", edicao=publicado.turma.edicao)

    paginas = {
        "projeto publicado": client.get(f"/projeto/{publicado.slug}/"),
        "projeto de edição passada": client.get(f"/projeto/{antigo.slug}/"),
        "projeto 404": client.get("/projeto/nao-existe/"),
        "como votar": client.get("/como-votar/"),
        "grupo GET": client.get("/grupo/"),
        "grupo RA recusado": client.post("/grupo/", {"ra": "9999999"}),
        "grupo link": client.post("/grupo/", {"ra": "2026001"}),
        "link inválido": client.get("/grupo/editar/naoexiste/"),
    }
    cache.set(servicos.chave_falhas_global(), servicos.LIMITE_FALHAS_GLOBAL, 60)
    paginas["grupo 429"] = client.post("/grupo/", {"ra": "9999999"})
    for onde, resposta in paginas.items():
        _confere(resposta.content.decode(), onde)


@pytest.mark.django_db
def test_tela_de_edicao_em_todos_os_estados(client):
    # editável, em ajustes, com motivo, equipe, capa e galeria
    p, token = _projeto_completo()
    p.status = Projeto.Status.AJUSTES
    p.motivo_ajustes = "Troque a capa.\nMelhore o resumo."
    p.save(update_fields=["status", "motivo_ajustes", "atualizado_em"])
    url = f"/grupo/editar/{token}/"
    dados = aux.dados_de_edicao(integrantes=(("Ana", "Front-end"),))

    paginas = {
        "editar GET": client.get(url),
        "editar com erro de campo": client.post(url, aux.dados_de_edicao(resumo="r" * 281)),
        "editar com 11 integrantes": client.post(url, aux.dados_de_edicao(integrantes=[(f"P{i}", "") for i in range(11)])),
        "editar ação inválida": client.post(url, {**dados, "acao": "x"}),
        "upload inválido": client.post(
            f"{url}imagem/", {"tipo": "extra", "arquivo": fabricas.imagem("GIF", "a.gif")}
        ),
    }
    # pendências ao enviar (projeto sem capa)
    sem_capa, token_sem_capa = aux.projeto_com_link(edicao=p.turma.edicao, ra_hmac=aux.hash_ra("7654321"))
    paginas["editar com pendências"] = client.post(f"/grupo/editar/{token_sem_capa}/", aux.dados_de_edicao(acao="enviar"))
    # etec
    etec, token_etec = aux.projeto_com_link(
        unidade="etec", edicao=p.turma.edicao, ra_hmac=aux.hash_ra("1357913")
    )
    paginas["editar Etec GET"] = client.get(f"/grupo/editar/{token_etec}/")
    paginas["editar Etec nome composto"] = client.post(
        f"/grupo/editar/{token_etec}/", aux.dados_de_edicao(integrantes=(("Ana Souza", ""),))
    )
    # com mensagem de sucesso (redirect seguido)
    paginas["editar após salvar"] = client.post(url, dados, follow=True)
    for onde, resposta in paginas.items():
        _confere(resposta.content.decode(), onde)


@pytest.mark.django_db
@pytest.mark.parametrize("cenario", ["em_revisao", "publicado", "prazo", "votacao_aberta"])
def test_tela_de_edicao_somente_leitura(client, cenario):
    if cenario in ("em_revisao", "publicado"):
        status = Projeto.Status.EM_REVISAO if cenario == "em_revisao" else Projeto.Status.PUBLICADO
        p, token = _projeto_completo(status=status)
    else:
        p, token = _projeto_completo()
        (aux.prazo_vencido if cenario == "prazo" else aux.votacao_aberta)(p)
    url = f"/grupo/editar/{token}/"
    _confere(client.get(url).content.decode(), f"leitura {cenario} GET")
    _confere(client.post(url, aux.dados_de_edicao()).content.decode(), f"leitura {cenario} POST 403")
    _confere(
        client.post(f"{url}imagem/", {"tipo": "capa", "arquivo": fabricas.imagem()}).content.decode(),
        f"leitura {cenario} upload 403",
    )
