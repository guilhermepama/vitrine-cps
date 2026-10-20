"""Contrato entre a tela de edição e os scripts opcionais (specs/07-pagina-inicial.md, "Tela de edição do grupo").

`static/js/imagens.js` e `static/js/aviso-ao-sair.js` localizam os elementos por estes
seletores; se o HTML mudar e um deles sumir, o script desliga em silêncio (melhoria
progressiva). A lista abaixo é exatamente a dos `getElementById`, `querySelector`,
`getAttribute("data-…")` e `hasAttribute` dos dois scripts — ao mudar um, mude aqui. O
`aviso-salvar-texto` e `.edicao-upload__estado` são procurados mas opcionais no script.
"""

import re

import pytest
from django.conf import settings

from cadastro.models import ImagemProjeto
from cadastro.tests import fabricas
from vitrine.tests import auxiliares as aux

# imagens.js — (trecho que o HTML servido precisa ter, termo que o script usa para achá-lo).
# `.previa`, `.edicao-upload__estado` e `.aviso-flutuante` o script cria sozinho quando faltam.
CONTRATO_IMAGENS = [
    ('id="imagens"', 'getElementById("imagens")'),               # a seção trocada pela resposta
    ('class="envio"', 'querySelector(".envio")'),                 # o painel "O que falta"
    ('class="container edicao__avisos"', ".edicao__avisos .alerta--ok"),  # mensagem de sucesso
    ('id="aviso-salvar-texto"', "#aviso-salvar-texto"),           # texto trocado quando o fetch está ativo
    ('data-previa="previa-capa"', 'getAttribute("data-previa")'),  # alvo da prévia da capa
    ('id="previa-capa"', 'getAttribute("data-previa")'),
    ('data-previa="previa-extra"', 'getAttribute("data-previa")'),  # alvo da prévia do card "+"
    ('id="previa-extra"', 'getAttribute("data-previa")'),
    ('class="edicao-upload__slot"', "edicao-upload__slot"),       # escondido/mostrado com a prévia
    ("data-envio-automatico", 'hasAttribute("data-envio-automatico")'),  # sobe ao escolher o arquivo
    ('class="adicionar"', 'querySelector(".adicionar")'),         # o card "+" é o seletor de arquivo
    ('class="legenda"', '"form.legenda"'),                         # legendas digitadas e não salvas
    ('class="legenda__campo"', ".legenda__campo"),                # valor × defaultValue
    ('class="edicao-upload__estado"', "edicao-upload__estado"),   # avisos por formulário
]

# aviso-ao-sair.js
CONTRATO_AVISO_AO_SAIR = [
    ('id="form-projeto"', 'getElementById("form-projeto")'),      # texto mexido e não salvo
    ('class="legenda__campo"', ".legenda__campo"),                # legenda mexida e não salva
]


def _tela_editavel():
    projeto, token = aux.projeto_com_link()
    aux.com_capa(projeto)
    ImagemProjeto.objects.create(projeto=projeto, arquivo=fabricas.imagem(), legenda="Tela", ordem=0)
    return projeto, token


@pytest.mark.django_db
def test_html_da_edicao_tem_os_seletores_que_os_scripts_usam(client):
    _, token = _tela_editavel()
    html = client.get(f"/grupo/editar/{token}/").content.decode()
    for trecho, _ in CONTRATO_IMAGENS + CONTRATO_AVISO_AO_SAIR:
        assert trecho in html, trecho
    assert 'src="/static/js/imagens.js" defer' in html and 'src="/static/js/aviso-ao-sair.js" defer' in html


@pytest.mark.django_db
def test_formularios_de_imagem_tem_arquivo_e_botao_de_envio(client):
    """prepararUpload desiste do formulário sem `input[type=file]`, `button[type=submit]` ou alvo da prévia."""
    _, token = _tela_editavel()
    html = client.get(f"/grupo/editar/{token}/").content.decode()
    formularios = re.findall(r"<form[^>]*data-previa=\"([^\"]+)\"[^>]*>(.*?)</form>", html, re.S)
    assert [alvo for alvo, _ in formularios] == ["previa-capa", "previa-extra"]
    for alvo, corpo in formularios:
        assert 'type="file"' in corpo and 'type="submit"' in corpo, alvo
        assert f'id="{alvo}"' in html
    # os formulários de legenda e remover: um botão submit cada, para o rótulo "Salvando…" voltar
    legendas = re.findall(r'<form class="legenda"[^>]*action="([^"]+)"[^>]*>(.*?)</form>', html, re.S)
    assert len(legendas) == 1 and 'type="submit"' in legendas[0][1] and "/legenda/" in legendas[0][0]


@pytest.mark.django_db
def test_somente_leitura_nao_carrega_os_scripts(client):
    projeto, token = aux.projeto_com_link()
    projeto.status = projeto.Status.EM_REVISAO
    projeto.save(update_fields=["status", "atualizado_em"])
    html = client.get(f"/grupo/editar/{token}/").content.decode()
    assert "imagens.js" not in html and "aviso-ao-sair.js" not in html
    assert 'id="imagens"' not in html and 'id="form-projeto"' not in html


def test_lista_de_seletores_bate_com_os_scripts():
    """Cada id/classe/atributo do contrato aparece no JS, e cada `getElementById` do JS está no contrato."""
    js = settings.BASE_DIR / "static" / "js"
    imagens = (js / "imagens.js").read_text(encoding="utf-8")
    aviso = (js / "aviso-ao-sair.js").read_text(encoding="utf-8")
    for _, termo in CONTRATO_IMAGENS:
        assert termo in imagens, termo
    for _, termo in CONTRATO_AVISO_AO_SAIR:
        assert termo in aviso, termo
    ids_no_js = set(re.findall(r'getElementById\("([\w-]+)"\)', imagens + aviso))
    ids_no_contrato = {re.search(r'id="([\w-]+)"', t).group(1) for t, _ in CONTRATO_IMAGENS + CONTRATO_AVISO_AO_SAIR if t.startswith("id=")}
    assert ids_no_js <= ids_no_contrato, ids_no_js - ids_no_contrato


def test_legenda_digitada_durante_o_envio_e_comparada_com_o_valor_enviado():
    """Revisão do Renan (rodada 2 do #75): escrever "Tela", salvar e, com a resposta pendente,
    seguir até "Tela inicial" não pode perder o "inicial". Sem runner de JS, o teste fixa o
    mecanismo no texto: `enviar` guarda o valor do campo no clique e `legendasMexidas` compara
    o formulário enviado com esse valor (não exclui mais o formulário incondicionalmente).
    """
    imagens = (settings.BASE_DIR / "static" / "js" / "imagens.js").read_text(encoding="utf-8")
    assert "form !== enviado" not in imagens
    assert 'var valorEnviado = legenda ? legenda.value : null;' in imagens
    assert "aplicar(res.html, form, valorEnviado)" in imagens
    assert "legendasMexidas(atual, enviado, valorEnviado)" in imagens
    assert "form === enviado ? valorEnviado : campo.defaultValue" in imagens
    # o que volta para o campo fica como não salvo (value ≠ defaultValue): nada de mexer no defaultValue
    assert "defaultValue =" not in imagens
