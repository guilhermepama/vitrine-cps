"""python manage.py medir_voto --url https://<ambiente> [--niveis 1,10,30] [--votos 10]

Mede a trava por voto (spec 03, "Referência temporal"; nota N3 do plano):
simula visitantes contra a URL pública — `/entrar` → `/visitantes` → `/votar`
→ V votos em `POST /votos` — e imprime p50, p95 e máximo do `POST /votos`
por nível de concorrência, com a contagem de 201/409/5xx.

Roda no shell da plataforma: assina o QR com o segredo do ambiente onde
roda, lido só do `settings` — nunca por argumento, nunca impresso (G3).
Só roda com a edição em votação chamada "pré-ensaio": cria tokens,
cadastros e votos de mentira nessa edição.

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
from http.cookies import SimpleCookie

from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

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

    def preparar(self, estacao_id):
        """`/entrar` → `/visitantes` → `/votar`. Devolve os ids da cédula."""
        ts = assinatura.agora()
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

    def votar(self, projeto_id):
        """(status, segundos) de um `POST /votos`; status 0 = sem resposta."""
        inicio = time.perf_counter()
        try:
            status, _ = self.pedir(
                reverse("votacao:votos"), {"projeto_id": projeto_id}, [("X-CSRFToken", self.cookies["csrftoken"])]
            )
        except OSError:
            status = 0
        return status, time.perf_counter() - inicio


class Distribuidor:
    """Escolhe a estação de cada emissão sem passar de 20 por bloco de 45 s."""

    def __init__(self, estacoes):
        self.estacoes, self.usadas, self.trava = estacoes, {}, threading.Lock()

    def proxima(self):
        while True:
            with self.trava:
                bloco = assinatura.agora() // assinatura.ROTACAO_QR
                for estacao_id in self.estacoes:
                    if self.usadas.get((estacao_id, bloco), 0) < limite.LIMITE_ESTACAO:
                        self.usadas[(estacao_id, bloco)] = self.usadas.get((estacao_id, bloco), 0) + 1
                        return estacao_id
            time.sleep(assinatura.ROTACAO_QR - assinatura.agora() % assinatura.ROTACAO_QR + 1)


def resumo(nivel, resultados):
    tempos = sorted(segundos * 1000 for status, segundos in resultados if status)
    contagem = {rotulo: 0 for rotulo in ("201", "409", "5xx", "outros")}
    for status, _ in resultados:
        rotulo = str(status) if status in (201, 409) else "5xx" if status >= 500 else "outros"
        contagem[rotulo] += 1
    p95 = statistics.quantiles(tempos, n=20, method="inclusive")[18] if len(tempos) > 1 else (tempos or [0])[0]
    return (
        f"{nivel:>3} simultâneos | {len(resultados):>4} votos | "
        f"p50 {statistics.median(tempos) if tempos else 0:7.1f} ms | p95 {p95:7.1f} ms | "
        f"máx {max(tempos, default=0):7.1f} ms | "
        + " ".join(f"{rotulo} {n}" for rotulo, n in contagem.items())
    )


class Command(BaseCommand):
    help = 'Mede a latência do POST /votos sob concorrência (só na edição "pré-ensaio").'

    def add_arguments(self, parser):
        parser.add_argument("--url", required=True, help="URL pública do ambiente, ex.: https://vitrine.exemplo")
        parser.add_argument("--niveis", default="1,10,30", help="Visitantes simultâneos por rodada.")
        parser.add_argument("--votos", type=int, default=10, help="Votos por visitante.")

    def handle(self, *args, url, niveis, votos, **options):
        edicao = edicao_em_votacao()
        if edicao is None or NOME_EXIGIDO not in edicao.nome.casefold():
            raise CommandError(f'Só roda com a votação aberta numa edição com "{NOME_EXIGIDO}" no nome.')
        try:
            niveis = [int(n) for n in niveis.split(",")]
        except ValueError:
            raise CommandError("--niveis: inteiros separados por vírgula, ex.: 1,10,30.")
        if votos < 1 or min(niveis) < 1:
            raise CommandError("--niveis e --votos precisam ser maiores que zero.")
        estacoes = list(Estacao.objects.filter(edicao=edicao, ativa=True).order_by("pk").values_list("pk", flat=True))
        if not estacoes:
            raise CommandError("A edição não tem estação ativa.")
        emissoes = sum(niveis)
        if emissoes > limite.LIMITE_IP:
            raise CommandError(f"{emissoes} emissões passam do limite de {limite.LIMITE_IP} por IP em 10 min.")
        self.stdout.write(f"Edição {edicao.nome}: {len(estacoes)} estação(ões), {emissoes} emissão(ões) no total.")
        distribuidor = Distribuidor(estacoes)
        for nivel in niveis:
            self.stdout.write(resumo(nivel, self._rodada(url, nivel, votos, distribuidor)))

    def _rodada(self, url, nivel, votos, distribuidor):
        """Prepara `nivel` visitantes e só então solta todos votando juntos."""
        visitantes = [Visitante(url) for _ in range(nivel)]
        largada = threading.Barrier(nivel)

        def visitar(visitante):
            try:
                projetos = visitante.preparar(distribuidor.proxima())
                if len(projetos) < votos:
                    raise RuntimeError(f"A cédula tem {len(projetos)} projeto(s) para {votos} voto(s).")
            except BaseException:
                largada.abort()  # ninguém fica esperando quem não vai chegar
                raise
            largada.wait(PRAZO * 4)
            return [visitante.votar(projeto_id) for projeto_id in projetos[:votos]]

        with ThreadPoolExecutor(max_workers=nivel) as executor:
            futuros = [executor.submit(visitar, v) for v in visitantes]
        erros = [f.exception() for f in futuros if f.exception()]
        # O erro de quem falhou, não o BrokenBarrierError de quem esperava por ele.
        erros.sort(key=lambda erro: isinstance(erro, threading.BrokenBarrierError))
        if erros:
            raise CommandError(f"Falhou ao preparar os visitantes: {erros[0]}")
        return [r for futuro in futuros for r in futuro.result()]
