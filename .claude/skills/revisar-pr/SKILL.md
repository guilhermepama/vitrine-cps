---
name: revisar-pr
description: Revisar um pull request do Vitrine CPS contra a spec do módulo e os guardrails. Usar quando um PR estiver aberto aguardando revisão — a IA prepara a análise, o humano decide.
---

# Revisar um PR

> A IA levanta os achados; quem aprova é o revisor humano (guardrail 18).

1. Identifique a spec referenciada pelo PR. PR com código e sem spec →
   devolver. PR só de documentação ou processo (ADR, guardrail,
   `TAREFAS.md`, skills) não tem spec: a referência é a ADR ou o
   guardrail que ele cria ou altera — confira a coerência entre os
   arquivos tocados e o G20 (mudança em guardrail só com registro em
   `docs/02-decisoes.md`). Nesse caso, os passos 2 a 4 valem contra essa
   referência, e o passo 4 vira "n/a" quando não há código.
2. Verifique escopo: tudo que o diff faz está na spec? Liste qualquer
   coisa a mais (mesmo "melhoria") — fora de escopo é achado.
3. Percorra os guardrails listados na spec, um a um, e aponte onde o diff
   atende ou viola cada um. Atenção especial:
   - 4 — unicidade `(token_id, projeto_id)` como constraint NO BANCO
   - 5 — respostas de rejeição idênticas e genéricas
   - 6 — nenhum vínculo `visitantes` ↔ token/voto
   - 13 — nenhuma query com string interpolada
4. Confira os critérios de aceite da spec contra os testes do PR — critério
   sem teste correspondente é achado.
5. Procure segredos, `.env`, logs com dados pessoais e `console.log`
   esquecido.
6. Produza o parecer em 3 blocos: **bloqueante** (viola guardrail/escopo),
   **recomendado**, **cosmético**. Sem bloqueantes ≠ aprovado — a decisão
   é do revisor humano.
