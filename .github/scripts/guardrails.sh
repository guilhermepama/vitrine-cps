#!/usr/bin/env bash
# Verificação automática dos guardrails (docs/01-guardrails.md) que dá para
# checar sem conhecer a stack. É heurística: pega o erro óbvio e barato.
# Não substitui a revisão humana (guardrail 18).
#
# Uso: .github/scripts/guardrails.sh [diretório-do-repo]
# Saída: 0 = ok (pode ter avisos) | 1 = violação bloqueante
#
# Falso positivo? Reescreva o trecho ou fale com o coordenador — este
# arquivo é protegido por CODEOWNERS; não há "comentário de escape".

set -uo pipefail

ROOT="${1:-.}"
cd "$ROOT" || exit 2

ERROS=0
AVISOS=0

erro() {  # $1 = guardrail, $2 = mensagem, $3 = ocorrências
  ERROS=$((ERROS + 1))
  echo "::error title=Guardrail $1::$2"
  [ -n "${3:-}" ] && printf '%s\n' "$3" | sed 's/^/    /'
}
aviso() {
  AVISOS=$((AVISOS + 1))
  echo "::warning title=Guardrail $1::$2"
  [ -n "${3:-}" ] && printf '%s\n' "$3" | sed 's/^/    /'
}

# Arquivos rastreados pelo git. Documentação, specs e instruções de agentes
# falam DOS guardrails (contêm "CPF", "token" etc.) e por isso ficam de fora.
mapfile -t TODOS < <(git ls-files)
CODIGO=()
for f in "${TODOS[@]}"; do
  case "$f" in
    docs/*|specs/*|.claude/*|.cursor/*|skills-seed/*|.github/*) continue ;;
    *.md|*.mdc|*.txt|*.pdf|*.png|*.jpg|*.jpeg|*.gif|*.svg|*.webp|*.ico) continue ;;
    .env.example|.gitignore|.gitattributes|LICENSE) continue ;;
  esac
  [ -f "$f" ] && CODIGO+=("$f")
done

busca() {  # grep nos arquivos de código; $@ = opções + padrão
  [ ${#CODIGO[@]} -eq 0 ] && return 0
  grep -nIE "$@" -- "${CODIGO[@]}" 2>/dev/null || true
}

# --- G3: .env real ou segredo HMAC no código -------------------------------
ENVS=$(printf '%s\n' "${TODOS[@]}" | grep -E '(^|/)\.env($|\.)' | grep -vE '(^|/)\.env\.example$' || true)
[ -n "$ENVS" ] && erro 3 "Arquivo .env commitado. Remova do git (git rm --cached) — só .env.example vai para o repositório." "$ENVS"

HIT=$(busca "QR_HMAC_SECRET[\"']?[[:space:]]*[:=][[:space:]]*[\"'][^\"'\$]{8,}")
[ -n "$HIT" ] && erro 3 "Segredo HMAC com valor fixo no código. Ele vive só em variável de ambiente." "$HIT"

# --- G6: vínculo visitantes <-> token/voto ---------------------------------
HIT=$(busca -i '(visitantes?|visitors?)[^[:space:]]{0,3}[._]?[[:alnum:]_]*(token_?id|tokenid|voto_?id|vote_?id)')
[ -n "$HIT" ] && erro 6 "Possível vínculo entre visitantes e token/voto. Isso quebra o anonimato do voto (ADR-003)." "$HIT"

# Bloco CREATE TABLE visitantes ... ; com coluna de token/voto (SQL puro)
for f in "${CODIGO[@]}"; do
  case "$f" in *.sql) ;; *) continue ;; esac
  BLOCO=$(awk '{l=tolower($0)} l~/create[[:space:]]+table[^;(]*visitantes/{on=1} on{print FILENAME":"NR": "$0} on&&l~/;/{on=0}' "$f" | grep -iE 'token|voto|vote' || true)
  [ -n "$BLOCO" ] && erro 6 "Tabela visitantes com coluna ligada a token/voto em $f." "$BLOCO"
done

# --- G9: dados pessoais proibidos ------------------------------------------
HIT=$(busca -i '\b(cpf|numero_?rg|rg_?(number|numero)|data_?(de_?)?nascimento|birth_?date|date_?of_?birth)\b')
[ -n "$HIT" ] && erro 9 "Campo de dado pessoal proibido (CPF/RG/nascimento). Coletar só nome, email, telefone e consentimento." "$HIT"

# --- G13: SQL montado com interpolação -------------------------------------
SQL='(SELECT|INSERT|UPDATE|DELETE)[[:space:]]'
HIT=$(
  busca "\`[^\`]*${SQL}[^\`]*\\$\\{"                    # JS/TS template literal com ${}
  for q in '"' "'"; do
    busca "f${q}[^${q}]*${SQL}[^${q}]*\\{"                    # Python f-string
    busca "${q}[^${q}]*${SQL}[^${q}]*${q}[[:space:]]*(\\+|\\.|%[[:space:]])" # concatenação / % / PHP .
    busca "${q}[^${q}]*${SQL}[^${q}]*${q}\\.format\\("         # str.format
  done
)
[ -n "$HIT" ] && erro 13 "SQL montado com interpolação/concatenação. Use query parametrizada." "$HIT"

# --- G11 / higiene: console.log esquecido -----------------------------------
HIT=$(busca 'console\.log\(')
[ -n "$HIT" ] && aviso 11 "console.log no código — confira se não vaza dado de visitante/token e remova antes do merge." "$HIT"

echo
echo "Guardrails: ${#CODIGO[@]} arquivo(s) de código verificados — ${ERROS} erro(s), ${AVISOS} aviso(s)."
[ "$ERROS" -eq 0 ]
