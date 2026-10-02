"""Leitura do arquivo .env no desenvolvimento local.

Substitui o python-dotenv (fora da lista da ADR-002) com o mínimo:
linhas CHAVE=VALOR, comentários com #, aspas opcionais. Nunca sobrescreve
uma variável que já existe no ambiente.
"""

import os


def carregar_env(caminho):
    if not caminho.is_file():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave = chave.strip()
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        if chave:
            os.environ.setdefault(chave, valor)
