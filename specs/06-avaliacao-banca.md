# Spec — Avaliação da banca

> Stub — completar usando `specs/_template.md` antes de implementar.
> Regras de negócio já decididas na ADR-007.

- **Responsável**: (a definir em TAREFAS.md)
- **Status**: rascunho
- **Depende de**: ADR-002, ADR-007, spec 01 (projetos e turmas)

## Objetivo
Permitir que jurados autenticados deem nota 0–10, por critério, aos
projetos da edição, no próprio celular.

## Escopo (já decidido — detalhar)
- Critérios cadastrados por edição no admin (nome, ordem).
- Jurado = usuário do Django no grupo "banca"; login próprio.
- Tela do jurado: lista de projetos por turma, marca os já avaliados;
  formulário com uma nota por critério.
- Uma avaliação por (jurado, projeto, critério) — constraint no banco;
  jurado pode corrigir a própria nota enquanto a avaliação estiver aberta.
- Plano B: lançamento das notas pelo admin a partir de ficha impressa.

## Fora de escopo
- Cálculo da nota final (spec 04).
- Qualquer vínculo com tokens ou votos do público.

## Guardrails aplicáveis
12, 13, 15, 16, 17.

## Critérios de aceite
- [ ] (a detalhar)
