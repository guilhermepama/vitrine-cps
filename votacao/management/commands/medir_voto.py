"""python manage.py medir_voto [--url https://<ambiente>] [--niveis 1,10,30] [--votos 10]

Mede a trava por voto (spec 03, "Referência temporal" e "Decisões do PR #37"):
simula visitantes contra a URL pública — `/entrar` → `/visitantes` → `/votar`
→ V votos em `POST /votos` — e imprime p50, p95 e máximo do `POST /votos`
por nível de concorrência, com a contagem de 201/409/5xx. Antes dos votos,
os mesmos visitantes fazem V `GET /votar` juntos: é a linha de base sem a
trava da `Edicao`, no mesmo nível, que separa a fila do servidor (workers,
conexão, banco) da espera pela trava.

Roda no shell da plataforma: assina o QR com o segredo do ambiente onde
roda, lido só do `settings` — nunca por argumento, nunca impresso (G3).
Só roda com a edição em votação cujo nome começa por "Pré-ensaio" —
conferida no início e antes de cada rodada — e com o host do `--url` em
`ALLOWED_HOSTS` (o banco conferido é o do mesmo ambiente; `"*"` é recusado,
porque aceitaria qualquer host). Antes da primeira rodada, uma sonda (1
visitante, sem votar) confere que a cédula devolvida pelo `--url` tem
exatamente os projetos publicados da edição local; cada visitante confere de
novo antes de votar. Se o alvo for outro ambiente, nenhum voto sai e, no
pior caso, fica lá 1 token e 1 cadastro da sonda. A conferência compara ids:
é heurística, não prova que é o mesmo banco. Cria tokens, cadastros e votos
de mentira nessa edição, que ficam no banco (decisão do coordenador no
PR #37).

Respeita o rate limit (G7): cada estação ativa emite no máximo 20 tokens por
bloco de 45 s; com todas esgotadas, espera o bloco seguinte. O limite de
300 emissões por IP em 10 min fica de pé: um visitante simulado = 1 emissão.
"""

import re
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPException
from http.cookies import SimpleCookie

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.http.request import validate_host
from django.urls import reverse

from cadastro.models import Projeto
from votacao import assinatura, limite
from votacao.models import Estacao
from votacao.servicos import edicao_em_votacao

NOME_EXIGIDO = "pré-ensaio"
PRAZO = 30  # segundos por requisição
_CSRF_FORM = re.compile(r'name="csrfmiddlewaretoken" value="([^"]+)"')
_PROJETO = re.compile(r'data-projeto="([0-9]+)"')


class _SemRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # o 302 volta como resposta: os cookies dele importam


class Visitante:
    """Um navegador: cookies próprios, guardados à mão (o `http.cookiejar` não
    devolve cookie `Secure` em http, e o teste roda em http)."""

    def __init__(self, base):
        self.base = base.rstrip("/")
        self.cookies = {}
        self.abridor = urllib.request.build_opener(_SemRedirect)

    def pedir(self, caminho, dados=None, cabecalhos=()):
        corpo = urllib.parse.urlencode(dados).encode() if dados is not None else None
        pedido = urllib.request.Request(self.base + caminho, data=corpo, headers=dict(cabecalhos))
        if self.cookies:
            pedido.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in self.cookies.items()))
        if corpo is not None:
            pedido.add_header("Origin", self.base)
            pedido.add_header("Referer", self.base + caminho)
        try:
            resposta = self.abridor.open(pedido, timeout=PRAZO)
        except urllib.error.HTTPError as erro:
            resposta = erro
        with resposta:
            for linha in resposta.headers.get_all("Set-Cookie") or []:
                for nome, morsel in SimpleCookie(linha).items():
                    self.cookies[nome] = morsel.value
            return resposta.status, resposta.read().decode("utf-8", "replace")

    def preparar(self, estacao_id, ts):
        """`/entrar` → `/visitantes` → `/votar`. Devolve os ids da cédula.

        O `ts` é o do distribuidor: o servidor conta no mesmo bloco de 45 s.
        """
        query = urllib.parse.urlencode({"w": f"{estacao_id}:{ts}", "sig": assinatura.assinar(estacao_id, ts)})
        self._esperar(200, reverse("votacao:entrar") + "?" + query)
        formulario = self._esperar(200, reverse("votacao:visitantes"))
        dados = {
            "csrfmiddlewaretoken": _CSRF_FORM.search(formulario)[1],
            "nome": "Visitante da medição",
            "email": "medicao@example.com",
            "consentimento": "on",
        }
        self._esperar(302, reverse("votacao:visitantes"), dados)
        return [int(i) for i in _PROJETO.findall(self._esperar(200, reverse("votacao:votar")))]

    def _esperar(self, status, caminho, dados=None):
        recebido, corpo = self.pedir(caminho, dados)
        if recebido != status:
            raise RuntimeError(f"{caminho.split('?')[0]} respondeu {recebido}, esperado {status}")
        return corpo

    def abrir_cedula(self):
        """(status, segundos) de um `GET /votar` — a linha de base, sem trava."""
        inicio = time.perf_counter()
        try:
            status, _ = self.pedir(reverse("votacao:votar"))
        except (OSError, HTTPException):
            status = 0
        return status, time.perf_counter() - inicio

    def votar(self, projeto_id):
        """(status, segundos) de um `POST /votos`; status 0 = sem resposta."""
        inicio = time.perf_counter()
        try:
            status, _ = self.pedir(
                reverse("votacao:votos"), {"projeto_id": projeto_id}, [("X-CSRFToken", self.cookies["csrftoken"])]
            )
        except (OSError, HTTPException):  # timeout, conexão caída, resposta truncada
            status = 0
        return status, time.perf_counter() - inicio


class Distribuidor:
    """Escolhe a estação e o `ts` de cada emissão sem passar de 20 por bloco de 45 s."""

    def __init__(self, estacoes):
        self.estacoes, self.usadas, self.trava = estacoes, {}, threading.Lock()

    def proxima(self):
        while True:
            with self.trava:
                ts = assinatura.agora()
                bloco = ts // assinatura.ROTACAO_QR
                for estacao_id in self.estacoes:
                    if self.usadas.get((estacao_id, bloco), 0) < limite.LIMITE_ESTACAO:
                        self.usadas[(estacao_id, bloco)] = self.usadas.get((estacao_id, bloco), 0) + 1
                        return estacao_id, ts
            time.sleep(assinatura.ROTACAO_QR - assinatura.agora() % assinatura.ROTACAO_QR + 1)


def resumo(nivel, resultados, *, base=False):
    """Uma linha por nível. `base=True`: a linha de base (`GET /votar`, sem trava)."""
    # Sem resposta (status 0) conta com o tempo que esperou: o timeout pesa no p95 e no máx.
    tempos = sorted(segundos * 1000 for _, segundos in resultados)
    esperados = (200,) if base else (201, 409)
    contagem = {rotulo: 0 for rotulo in (*map(str, esperados), "5xx", "outros")}
    for status, _ in resultados:
        rotulo = str(status) if status in esperados else "5xx" if status >= 500 else "outros"
        contagem[rotulo] += 1
    p95 = statistics.quantiles(tempos, n=20, method="inclusive")[18] if len(tempos) > 1 else (tempos or [0])[0]
    return (
        f"{nivel:>3} simultâneos | {len(resultados):>4} {'cédulas' if base else 'votos'} | "
        f"p50 {statistics.median(tempos) if tempos else 0:7.1f} ms | p95 {p95:7.1f} ms | "
        f"máx {max(tempos, default=0):7.1f} ms | "
        + " ".join(f"{rotulo} {n}" for rotulo, n in contagem.items())
    )


def _pre_ensaio():
    """Edição em votação, se o nome começa por "Pré-ensaio"; senão CommandError."""
    edicao = edicao_em_votacao()
    if edicao is None or not edicao.nome.casefold().startswith(NOME_EXIGIDO):
        raise CommandError(f'Só roda com a votação aberta numa edição cujo nome começa por "{NOME_EXIGIDO}".')
    return edicao


class Command(BaseCommand):
    help = 'Mede a latência do POST /votos sob concorrência (só na edição "pré-ensaio").'

    def add_arguments(self, parser):
        parser.add_argument("--url", help="URL pública do ambiente (padrão: settings.URL_PUBLICA).")
        parser.add_argument("--niveis", default="1,10,30", help="Visitantes simultâneos por rodada.")
        parser.add_argument("--votos", type=int, default=10, help="Votos por visitante.")

    def handle(self, *args, url, niveis, votos, **options):
        url = url or settings.URL_PUBLICA  # a origem pública deste mesmo ambiente (ADR-006)
        partes = urllib.parse.urlsplit(url)
        if partes.scheme not in ("http", "https") or not partes.hostname:
            raise CommandError("--url precisa ser http:// ou https:// com um host.")
        if "*" in settings.ALLOWED_HOSTS:
            raise CommandError('ALLOWED_HOSTS com "*" não garante que o --url é este ambiente: recusado.')
        if not validate_host(partes.hostname, settings.ALLOWED_HOSTS):
            raise CommandError("O host do --url não está em ALLOWED_HOSTS: rode no shell do próprio ambiente.")
        edicao = _pre_ensaio()
        try:
            niveis = [int(n) for n in niveis.split(",")]
        except ValueError:
            raise CommandError("--niveis: inteiros separados por vírgula, ex.: 1,10,30.")
        if votos < 1 or min(niveis) < 1:
            raise CommandError("--niveis e --votos precisam ser maiores que zero.")
        estacoes = list(Estacao.objects.filter(edicao=edicao, ativa=True).order_by("pk").values_list("pk", flat=True))
        if not estacoes:
            raise CommandError("A edição não tem estação ativa.")
        # Conferido antes de qualquer emissão: falhar aqui não gasta token nem cadastro.
        self.publicados = set(
            Projeto.objects.filter(status=Projeto.Status.PUBLICADO, turma__edicao=edicao).values_list("pk", flat=True)
        )
        if votos > len(self.publicados):
            raise CommandError(f"--votos {votos} passa dos {len(self.publicados)} projeto(s) publicados da edição.")
        emissoes = sum(niveis) + 1  # + a sonda
        if emissoes > limite.LIMITE_IP:
            raise CommandError(f"{emissoes} emissões passam do limite de {limite.LIMITE_IP} por IP em 10 min.")
        self.stdout.write(f"Edição {edicao.nome}: {len(estacoes)} estação(ões), {emissoes} emissão(ões) no total.")
        self.stdout.write(
            "Linha 'cédulas' = GET /votar (sem trava), mesmo nível; linha 'votos' = POST /votos (com a trava)."
        )
        distribuidor = Distribuidor(estacoes)
        self._sondar(url, distribuidor)
        for nivel in niveis:
            if _pre_ensaio().pk != edicao.pk:
                raise CommandError("A edição em votação mudou no meio da medição: parei antes da rodada seguinte.")
            base, resultados = self._rodada(url, nivel, votos, distribuidor)
            self.stdout.write(resumo(nivel, base, base=True))
            self.stdout.write(resumo(nivel, resultados))

    def _sondar(self, url, distribuidor):
        """Um visitante, sem votar: confere a cédula do --url antes de soltar a rodada.

        Se o alvo for outro ambiente, o estrago fica em 1 token e 1 cadastro lá,
        não em um por visitante da primeira rodada.
        """
        try:
            projetos = Visitante(url).preparar(*distribuidor.proxima())
        except (OSError, HTTPException, RuntimeError) as erro:
            raise CommandError(f"A sonda falhou: {type(erro).__name__}: {erro}")
        if set(projetos) != self.publicados:
            raise CommandError("A cédula do --url não é a da edição local: outro ambiente? Nenhum voto enviado.")

    def _rodada(self, url, nivel, votos, distribuidor):
        """Prepara `nivel` visitantes; solta todos juntos abrindo a cédula (linha
        de base) e depois, de novo juntos, votando. Devolve (base, votos)."""
        visitantes = [Visitante(url) for _ in range(nivel)]
        largada, segunda = threading.Barrier(nivel), threading.Barrier(nivel)

        def visitar(visitante):
            try:
                projetos = visitante.preparar(*distribuidor.proxima())
                if set(projetos) != self.publicados:
                    raise RuntimeError("A cédula do --url não é a da edição local: outro ambiente? Nenhum voto enviado.")
            except BaseException:
                largada.abort()  # ninguém fica esperando quem não vai chegar
                raise
            largada.wait(PRAZO * 4)
            base = [visitante.abrir_cedula() for _ in range(votos)]
            segunda.wait(PRAZO * 4 * votos)
            return base, [visitante.votar(projeto_id) for projeto_id in projetos[:votos]]

        with ThreadPoolExecutor(max_workers=nivel) as executor:
            futuros = [executor.submit(visitar, v) for v in visitantes]
        erros = [f.exception() for f in futuros if f.exception()]
        # O erro de quem falhou, não o BrokenBarrierError de quem esperava por ele.
        erros.sort(key=lambda erro: isinstance(erro, threading.BrokenBarrierError))
        if erros:
            raise CommandError(f"Falhou ao preparar os visitantes: {type(erros[0]).__name__}: {erros[0]}")
        base = [r for futuro in futuros for r in futuro.result()[0]]
        return base, [r for futuro in futuros for r in futuro.result()[1]]
