---
name: implementar-spec
description: Implementar um módulo do Vitrine CPS a partir de uma spec pronta, respeitando os guardrails. Usar quando a spec do módulo estiver com status "pronta para implementar" e a ADR-002 (stack) estiver aceita.
---

# Implementar uma spec

## Pré-condições (pare se alguma falhar)
- `docs/02-decisoes.md` → ADR-002 com status "aceita". Sem stack, sem código.
- A spec do módulo com status "pronta para implementar" e sem perguntas em
  aberto bloqueantes.

## Passos
1. Leia `docs/03-estado.md`, a spec inteira e CADA guardrail listado na
   seção "Guardrails aplicáveis" dela (`docs/01-guardrails.md`).
2. Crie a branch `feat/<modulo>-<resumo>`.
3. Implemente SOMENTE o escopo da spec. Ideia melhor fora do escopo →
   proposta em `docs/02-decisoes.md` (status: proposta), não código.
4. Alteração de schema → migration versionada + atualizar a seção "Dados"
   da spec no mesmo PR.
5. Escreva os testes dos critérios de aceite marcados como caminho crítico.
6. Antes de abrir o PR, auto-revisão contra os guardrails da spec, item a
   item, citando onde cada um é atendido no código.
7. Abra o PR referenciando a spec; marque os critérios de aceite atendidos.
8. Atualize `TAREFAS.md` (status) e acrescente uma linha no "Registro
   rápido" de `docs/03-estado.md`.
