---
name: nova-spec
description: Criar ou completar a spec de um módulo do Vitrine CPS a partir do template, no padrão da spec 03. Usar quando o responsável for especificar sua tarefa antes de gerar código.
---

# Criar/completar uma spec

1. Leia `docs/03-estado.md`, `docs/00-contexto.md` e `docs/02-decisoes.md`.
2. Abra `specs/_template.md` e a referência `specs/03-credenciamento-votacao.md`
   — a spec nova deve ter o mesmo nível de detalhe.
3. Preencha TODAS as seções. Regras:
   - "Fora de escopo" nunca fica vazio — é o que impede a IA de inventar.
   - "Comportamento esperado" cobre os caminhos de erro, não só o feliz.
   - "Guardrails aplicáveis" lista os números de `docs/01-guardrails.md`
     que a tarefa toca; releia cada um antes de fechar a spec.
   - Critérios de aceite verificáveis objetivamente (✓ ou ✗, sem "funciona bem").
4. Dúvida que trava a spec → registre em "Perguntas em aberto" e pergunte ao
   coordenador; não resolva sozinho com suposição.
5. Atualize o status da linha do módulo em `TAREFAS.md` para "spec pronta".
6. NÃO gere código nesta tarefa. Spec e código são entregas separadas.
