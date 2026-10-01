#!/usr/bin/env bash
# Convenções de PR do Vitrine CPS (AGENTS.md + guardrails de processo).
# Entradas por variável de ambiente (preenchidas pelo workflow):
#   PR_TITLE, PR_BODY, PR_BRANCH, BASE_SHA, HEAD_SHA
# Saída: 0 = ok (pode ter avisos) | 1 = bloqueante

set -uo pipefail

ERROS=0
erro()  { ERROS=$((ERROS + 1)); echo "::error title=$1::$2"; }
aviso() { echo "::warning title=$1::$2"; }

# Título vira a mensagem do commit (merge por squash) → mesmo padrão dos commits.
if ! printf '%s' "$PR_TITLE" | grep -qE '^[a-z0-9-]+: .{3,}'; then
  erro "Título do PR" "Use o padrão 'modulo: o que mudou' (ex: 'votacao: valida assinatura HMAC'). Recebido: '$PR_TITLE'"
fi

case "$PR_BRANCH" in
  feat/*|fix/*|spec/*|docs/*|chore/*) ;;
  *) aviso "Nome da branch" "Prefira feat/<modulo>-<resumo> (ou fix/, spec/, docs/, chore/). Recebido: '$PR_BRANCH'" ;;
esac

mapfile -t ALTERADOS < <(git diff --name-only "$BASE_SHA...$HEAD_SHA")
echo "Arquivos alterados: ${#ALTERADOS[@]}"

CODIGO=0; TESTES=0; GUARDRAILS=0; DECISOES=0
for f in "${ALTERADOS[@]}"; do
  case "$f" in
    docs/01-guardrails.md) GUARDRAILS=1 ;;
    docs/02-decisoes.md)   DECISOES=1 ;;
  esac
  case "$f" in
    docs/*|specs/*|.claude/*|.cursor/*|.github/*|skills-seed/*|*.md|*.mdc) continue ;;
    .gitattributes|.gitignore|.env.example|LICENSE) continue ;;
  esac
  CODIGO=1
  if printf '%s' "$f" | grep -qE '(^|/)(tests?|__tests__|e2e)/|\.(test|spec)\.[a-z]+$|_test\.[a-z]+$|(^|/)test_[^/]+\.py$'; then
    TESTES=1
  fi
done

# "Nenhum código sem spec" — o PR precisa apontar qual spec implementa.
if [ "$CODIGO" -eq 1 ] && ! printf '%s' "$PR_BODY" | grep -qE 'specs/[0-9]{2}-[a-z0-9-]+\.md'; then
  erro "Spec não referenciada" "PR com código precisa citar a spec no corpo (ex: specs/03-credenciamento-votacao.md). Sem spec, a entrega é a spec."
fi

# Guardrail 20 — mudança nos guardrails exige registro de decisão.
if [ "$GUARDRAILS" -eq 1 ] && [ "$DECISOES" -eq 0 ]; then
  erro "Guardrail 20" "docs/01-guardrails.md mudou sem registro em docs/02-decisoes.md."
fi

# Guardrail 17 — aviso (nem todo PR precisa de teste novo, mas o revisor deve olhar).
if [ "$CODIGO" -eq 1 ] && [ "$TESTES" -eq 0 ]; then
  aviso "Guardrail 17" "PR altera código sem tocar em nenhum teste. Revisor: confira se o caminho crítico está coberto."
fi

[ "$ERROS" -eq 0 ]
