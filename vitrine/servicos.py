"""Regras de negócio da vitrine e da área do grupo (spec 02).

Fica fora das views para ser testada sem HTTP. Regra da spec 01 para quem usa
os models: `status`, `slug` e `turma` mudam só por `save()` na instância ou
pelos métodos do model — nunca por `update()` em lote.
"""

import logging
import re
import time

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from cadastro.models import Edicao, Projeto
from cadastro.seguranca import chave_ip, hash_ra, hash_token, ip_do_cliente, token_confere

logger = logging.getLogger(__name__)

# --- Rate limit da reivindicação (spec 02, guardrail 7 por analogia) ----------
# Conta só falhas. Por IP é generoso: a turma toda sai pelo mesmo IP do Wi-Fi.
LIMITE_FALHAS_POR_IP = 50
JANELA_IP_SEGUNDOS = 10 * 60
LIMITE_FALHAS_GLOBAL = 1000
JANELA_GLOBAL_SEGUNDOS = 60 * 60


class EdicaoEncerrada(Exception):
    """O projeto não aceita mais edição (status, prazo ou votação aberta)."""


class PendenciasParaEnviar(Exception):
    def __init__(self, pendencias):
        super().__init__("Há pendências para enviar o projeto à revisão.")
        self.pendencias = pendencias


# --- Rate limit ---------------------------------------------------------------


def _balde(janela_segundos):
    # Janela fixa: cada janela tem a própria chave, que expira sozinha. O
    # `incr` do cache devolveria o prazo ao padrão (300 s) a cada contagem.
    return int(time.time() // janela_segundos)


def chave_falhas_ip(request):
    # O IP só existe como chave de cache, em hash com segredo (ADR-003).
    return f"rl:grupo:ip:{chave_ip(ip_do_cliente(request))}:{_balde(JANELA_IP_SEGUNDOS)}"


def chave_falhas_global():
    return f"rl:grupo:global:{_balde(JANELA_GLOBAL_SEGUNDOS)}"


def limite_estourado(request):
    return (
        cache.get(chave_falhas_ip(request), 0) >= LIMITE_FALHAS_POR_IP
        or cache.get(chave_falhas_global(), 0) >= LIMITE_FALHAS_GLOBAL
    )


def registrar_falha(request):
    # Prazo explícito de duas janelas: a chave da janela atual vive até o fim
    # dela. O DatabaseCache não é atômico: o limite é barreira contra abuso,
    # não contagem exata.
    for chave, janela in (
        (chave_falhas_ip(request), JANELA_IP_SEGUNDOS),
        (chave_falhas_global(), JANELA_GLOBAL_SEGUNDOS),
    ):
        cache.set(chave, cache.get(chave, 0) + 1, janela * 2)


# --- Reivindicação ------------------------------------------------------------


def _edicao_aceita_edicao(projeto):
    edicao = projeto.turma.edicao
    return edicao.edicao_aberta() and not edicao.votacao_foi_aberta()


def reivindicar(ra):
    """Devolve o token de edição em claro (mostrar uma vez) ou None.

    None cobre RA malformado, inexistente, já reivindicado, de outra edição,
    projeto fora de `pre_cadastrado`, RA duplicado e edição que não aceita
    mais edição — a view responde igual em todos os casos (guardrail 5 por
    analogia).
    """
    try:
        ra_hmac = hash_ra(ra)
    except ValueError:
        return None
    with transaction.atomic():
        # Até 2: a unicidade do RA por edição só é garantida em Projeto.clean(),
        # não no banco. Mais de um candidato = dado inconsistente (ex.: carga que
        # pulou o clean); ninguém é reivindicado e o admin corrige.
        candidatos = list(
            Projeto.objects.select_for_update(of=("self",))
            .select_related("turma__edicao")
            .filter(
                ra_hmac=ra_hmac,
                reivindicado_em__isnull=True,
                status=Projeto.Status.PRE_CADASTRADO,
                turma__edicao__ativa=True,
            )
            .order_by("pk")[:2]
        )
        if len(candidatos) > 1:
            logger.warning(
                "Mais de um projeto pré-cadastrado com o mesmo RA na edição ativa (projetos %s).",
                ", ".join(str(c.pk) for c in candidatos),
            )
            return None
        projeto = candidatos[0] if candidatos else None
        if projeto is None or not _edicao_aceita_edicao(projeto):
            return None
        projeto.reivindicado_em = timezone.now()
        projeto.save(update_fields=["reivindicado_em", "atualizado_em"])
        return projeto.regerar_link()


# --- Edição pelo link ---------------------------------------------------------


FORMATO_DO_TOKEN = re.compile(r"[A-Za-z0-9_-]{20,200}")


def projeto_do_token(token):
    # Formato fora do que `token_urlsafe` gera: 404 sem consultar o banco (G12).
    if not token or not FORMATO_DO_TOKEN.fullmatch(token):
        return None
    projeto = (
        Projeto.objects.select_related("turma__curso", "turma__edicao")
        .filter(token_edicao_hash=hash_token(token))
        .first()
    )
    if projeto is None or not token_confere(token, projeto.token_edicao_hash):
        return None
    return projeto


def motivo_somente_leitura(projeto):
    """None se o grupo pode editar; senão, o texto que a tela mostra."""
    if projeto.status == Projeto.Status.EM_REVISAO:
        return "Este projeto foi enviado para a revisão da coordenação. Para corrigir algo, fale com a coordenação."
    if projeto.status == Projeto.Status.PUBLICADO:
        return "Este projeto já foi publicado. Para corrigir algo, fale com a coordenação."
    if projeto.status not in (Projeto.Status.PRE_CADASTRADO, Projeto.Status.AJUSTES):
        return "Edição encerrada. Fale com a coordenação."
    if not _edicao_aceita_edicao(projeto):
        return "O prazo de edição acabou. Fale com a coordenação."
    return None


def pode_editar(projeto):
    return motivo_somente_leitura(projeto) is None


def travar_para_edicao(projeto_pk, token):
    """Trava a linha do projeto (dentro de uma transação) e confere se ainda é editável.

    Trava a `Edicao` primeiro e o `Projeto` depois, a mesma ordem do
    `Projeto.save()` e do admin (a ordem inversa causaria deadlock). Com as duas
    linhas travadas, confere de novo o prazo e a votação: nenhum "Salvar" grava
    depois que a votação abre. Confere também o token: se a coordenação regerou
    o link entre a leitura e a gravação, o link antigo não grava.
    """
    edicao_pk = Projeto.objects.values_list("turma__edicao_id", flat=True).get(pk=projeto_pk)
    Edicao.objects.select_for_update().get(pk=edicao_pk)
    projeto = (
        Projeto.objects.select_for_update(of=("self",))
        .select_related("turma__curso", "turma__edicao")
        .get(pk=projeto_pk)
    )
    if not token_confere(token, projeto.token_edicao_hash) or not pode_editar(projeto):
        raise EdicaoEncerrada
    return projeto


def enviar_para_revisao(projeto):
    """Confere as pendências no estado gravado e muda o status para `em_revisao`.

    Chamar dentro da mesma transação que gravou os campos: com pendências,
    levanta PendenciasParaEnviar e a transação inteira é desfeita.
    """
    pendencias = projeto.pendencias_para_publicar()
    if pendencias:
        raise PendenciasParaEnviar(pendencias)
    projeto.status = Projeto.Status.EM_REVISAO
    projeto.save(update_fields=["status", "atualizado_em"])


# --- Links absolutos ----------------------------------------------------------


def url_absoluta(caminho):
    """Base `settings.URL_PUBLICA` (ADR-006), nunca o `Host` da requisição."""
    if caminho.startswith(("http://", "https://")):
        return caminho
    return f"{settings.URL_PUBLICA}{caminho}"
