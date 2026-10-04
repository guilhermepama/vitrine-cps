"""Assinatura da janela do QR — fatia F3 (specs/03-credenciamento-votacao.md).

Critérios de aceite fechados aqui (parte unitária; a resposta HTTP idêntica
de `/entrar` fecha na F4):
- "`timestamp` em agora − 90s e agora + 5s → aceito; agora − 91s e
  agora + 6s → página 'QR expirado'"
- "`w` malformado (`abc`, `1:`, `:1700000000`, `01:1700000000`,
  `-1:1700000000`, 33 caracteres, `w` repetido) e `sig` malformado (63 e 65
  caracteres, maiúsculas, não hex, ausente)" → `ler_janela` devolve None
- G2: assinatura conferida com `hmac.compare_digest`; assinatura de outra
  estação ou de outro segredo não vale.
"""

import hashlib
import hmac
from unittest import mock
from urllib.parse import urlencode

import pytest
from django.http import QueryDict

from votacao import assinatura
from votacao.assinatura import assinar, ler_janela, nova_janela

AGORA = 1_793_000_000  # 2026-10-26, horário fixo dos testes
# Segredos fictícios, só para os testes; o real vem da variável de ambiente.
SEGREDO_TESTE = "segredo-de-teste"
SEGREDO_FORJADOR = "outro-segredo"
SEGREDO_SERVIDOR = "segredo-do-servidor"


@pytest.fixture(autouse=True)
def relogio():
    with mock.patch("votacao.assinatura.agora", return_value=AGORA) as fixo:
        yield fixo


def _query(**params):
    """QueryDict como o request.GET; listas viram parâmetros repetidos."""
    return QueryDict(urlencode(params, doseq=True))


def _valida(estacao_id=7, ts=AGORA):
    return {"w": f"{estacao_id}:{ts}", "sig": assinar(estacao_id, ts)}


def test_constantes_da_spec():
    assert assinatura.ROTACAO_QR == 45
    assert assinatura.TOLERANCIA_PASSADO == 90
    assert assinatura.TOLERANCIA_FUTURO == 5


def test_assinar_e_hmac_sha256_hex_minusculo_com_o_segredo_do_qr(settings):
    settings.QR_HMAC_SECRET = SEGREDO_TESTE
    esperado = hmac.new(SEGREDO_TESTE.encode(), b"7:1793000000", hashlib.sha256).hexdigest()
    assert assinar(7, AGORA) == esperado
    assert len(esperado) == 64 and esperado == esperado.lower()


def test_nova_janela_usa_o_relogio_do_servidor():
    assert nova_janela(7) == {"w": f"7:{AGORA}", "sig": assinar(7, AGORA)}


def test_janela_valida_devolve_estacao_e_timestamp():
    assert ler_janela(_query(**_valida())) == (7, AGORA)


def test_maior_id_de_estacao_aceito():
    assert ler_janela(_query(**_valida(2147483647))) == (2147483647, AGORA)


def test_espacos_nas_pontas_sao_removidos():
    valida = _valida()
    assert ler_janela(_query(w=f" {valida['w']} ", sig=f"{valida['sig']} ")) == (7, AGORA)


# Só o espaço ASCII sai das pontas (spec: "depois de remover espaços nas
# pontas"); qualquer outro branco Unicode fica e a matriz recusa.
BRANCOS_NAO_ASCII = {"\\x1f": "\x1f", "NBSP": "\xa0", "tab": "\t", "quebra de linha": "\n"}


@pytest.mark.parametrize("nome", BRANCOS_NAO_ASCII)
@pytest.mark.parametrize("ponta", ["inicio", "fim"])
@pytest.mark.parametrize("campo", ["w", "sig"])
def test_outros_brancos_nas_pontas_recusados(nome, ponta, campo):
    params = _valida()
    branco = BRANCOS_NAO_ASCII[nome]
    params[campo] = branco + params[campo] if ponta == "inicio" else params[campo] + branco
    assert ler_janela(_query(**params)) is None


def test_mais_cru_na_query_vira_espaco_e_e_aceito():
    # Na query string, "+" cru significa espaço (o QueryDict decodifica assim),
    # então `w=+7:<ts>` chega como " 7:<ts>" e, pela letra da spec, o espaço
    # ASCII da ponta é removido: a janela é aceita, já na forma canônica
    # (7, ts). Só o sinal de verdade (%2B) chega como "+" e é recusado.
    valida = _valida()
    assert ler_janela(QueryDict(f"w=+{valida['w']}&sig={valida['sig']}")) == (7, AGORA)
    assert ler_janela(QueryDict(f"w=%2B{valida['w']}&sig={valida['sig']}")) is None


def test_ler_janela_compara_em_tempo_constante():
    with mock.patch("votacao.assinatura.hmac.compare_digest", wraps=hmac.compare_digest) as comparar:
        assert ler_janela(_query(**_valida())) == (7, AGORA)
    comparar.assert_called_once()


# --- Janela de tempo: −90 s / +5 s ------------------------------------------


@pytest.mark.parametrize("deslocamento", [-90, -45, 0, 5])
def test_timestamp_dentro_da_tolerancia_aceito(deslocamento):
    assert ler_janela(_query(**_valida(ts=AGORA + deslocamento))) == (7, AGORA + deslocamento)


@pytest.mark.parametrize("deslocamento", [-91, 6, -3600, 3600])
def test_timestamp_fora_da_tolerancia_recusado(deslocamento):
    assert ler_janela(_query(**_valida(ts=AGORA + deslocamento))) is None


def test_url_capturada_expira(relogio):
    query = _query(**_valida())
    relogio.return_value = AGORA + 90
    assert ler_janela(query) == (7, AGORA)
    relogio.return_value = AGORA + 91
    assert ler_janela(query) is None


# --- Matriz de validação de w ------------------------------------------------

W_MALFORMADOS = [
    "abc",
    "1:",
    ":1700000000",
    "01:1700000000",
    "-1:1700000000",
    "+1:1700000000",
    "0:1700000000",
    "2147483648:1700000000",
    "12345678901:1700000000",
    "1:170000000",  # 9 dígitos
    "1:17000000000",  # 11 dígitos
    "1:0700000000",
    "1:-700000000",
    "1:1700000000:1",
    "1;1700000000",
    "1 :1700000000",
    "1:1700000000\n1",
    "١:1700000000",  # dígito arábico: \d casaria
    "1:１700000000",  # dígito de largura total
    "1" * 22 + ":1700000000",  # 33 caracteres
    "1:" + "1" * 31,  # 33 caracteres
    "",
]


@pytest.mark.parametrize("w", W_MALFORMADOS)
def test_w_malformado_recusado(w):
    assert ler_janela(_query(w=w, sig=assinar(1, 1700000000))) is None


def test_w_ausente_recusado():
    assert ler_janela(_query(sig=_valida()["sig"])) is None


def test_w_repetido_recusado_mesmo_com_os_dois_validos():
    valida = _valida()
    assert ler_janela(_query(w=[valida["w"], valida["w"]], sig=valida["sig"])) is None


# --- Matriz de validação de sig ----------------------------------------------


def _sigs_malformadas():
    sig = assinar(7, AGORA)
    return {
        "63 caracteres": sig[:63],
        "65 caracteres": sig + "a",
        "maiúsculas": sig.upper(),
        "não hex": "g" + sig[1:],
        "vazia": "",
    }


@pytest.mark.parametrize("caso", ["63 caracteres", "65 caracteres", "maiúsculas", "não hex", "vazia"])
def test_sig_malformada_recusada(caso):
    assert ler_janela(_query(w=f"7:{AGORA}", sig=_sigs_malformadas()[caso])) is None


def test_sig_ausente_recusada():
    assert ler_janela(_query(w=f"7:{AGORA}")) is None


def test_sig_repetida_recusada():
    sig = assinar(7, AGORA)
    assert ler_janela(_query(w=f"7:{AGORA}", sig=[sig, sig])) is None


def test_query_vazia_recusada():
    assert ler_janela(QueryDict("")) is None


# --- Assinatura forjada --------------------------------------------------------


def test_assinatura_de_outra_estacao_nao_vale():
    assert ler_janela(_query(w=f"8:{AGORA}", sig=assinar(7, AGORA))) is None


def test_assinatura_de_outro_timestamp_nao_vale():
    assert ler_janela(_query(w=f"7:{AGORA}", sig=assinar(7, AGORA - 45))) is None


def test_assinatura_de_outro_segredo_nao_vale(settings):
    settings.QR_HMAC_SECRET = SEGREDO_FORJADOR
    forjada = _valida()
    settings.QR_HMAC_SECRET = SEGREDO_SERVIDOR
    assert ler_janela(_query(**forjada)) is None
    assert ler_janela(_query(**_valida())) == (7, AGORA)
