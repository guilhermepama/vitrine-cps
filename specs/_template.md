# Spec — [Nome do módulo/tarefa]

> Copie este template para `specs/NN-nome.md`. A spec é o contrato da
> tarefa: o agente de IA implementa o que está aqui — nada além.
> Spec incompleta = a entrega é completar a spec, não escrever código.

- **Responsável**:
- **Status**: rascunho | pronta para implementar | em implementação | entregue
- **Depende de**: (outras specs/ADRs; ex: ADR-002 para qualquer código)

## Objetivo
Uma frase: o que este módulo entrega e para quem.

## Escopo
O que ESTÁ incluído nesta tarefa.

## Fora de escopo
O que explicitamente NÃO entra (evita a IA "melhorar" além do pedido).

## Comportamento esperado
Fluxos descritos passo a passo, incluindo os caminhos de erro.
Formato sugerido: "Quando X acontece, o sistema faz Y."

## Dados
Tabelas/campos que este módulo lê e escreve. Alterações de schema exigem
migration e menção explícita aqui.

## Endpoints / telas
Lista de rotas (método, caminho, entrada, saída, códigos de erro) ou telas
(o que exibe, o que valida, para onde navega).

## Guardrails aplicáveis
Números dos itens de `docs/01-guardrails.md` que esta tarefa toca
(ex: 1, 2, 5). O agente deve reler esses itens antes de implementar.

## Critérios de aceite
Checklist verificável. Se não dá para marcar ✓ objetivamente, reescreva.
- [ ] ...
- [ ] Testes do caminho crítico passando

## Perguntas em aberto
Dúvidas a resolver com o coordenador ANTES de implementar.
