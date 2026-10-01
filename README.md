# Vitrine CPS

Plataforma da mostra semestral de projetos da FATEC Olímpia e Etec (Centro
Paula Souza): cadastro de projetos por turma, página pública de divulgação
e votação presencial do público no dia do evento.

**Status**: início do código. Stack: Python + Django + PostgreSQL (ADR-002). Evento: 29/10/2026.

## Comece por aqui

| Arquivo | O que é |
|---|---|
| `docs/00-contexto.md` | O que é o sistema, atores, módulos e regras de negócio |
| `docs/01-guardrails.md` | Regras inegociáveis de segurança e qualidade |
| `docs/02-decisoes.md` | Registro de decisões de arquitetura (ADRs) |
| `docs/03-estado.md` | Estado atual do projeto — leia antes de retomar trabalho |
| `docs/referencias/cursos.md` | Cursos participantes (DSM, GTUR): semestres, projetos integradores, implicações para a modelagem |
| `specs/` | Uma spec por módulo — o contrato de cada tarefa |
| `TAREFAS.md` | Quem é responsável por qual módulo e ordem de dependências |
| `AGENTS.md` | Instruções para qualquer agente de IA (fonte única) |

## Fluxo de trabalho

1. Pegue seu módulo em `TAREFAS.md`.
2. Complete a spec dele em `specs/` (modelo: `specs/_template.md`;
   referência de qualidade: `specs/03-credenciamento-votacao.md`).
3. Gere o código com sua ferramenta de IA — ela deve ter lido `AGENTS.md`,
   os guardrails e a sua spec.
4. Branch `feat/<modulo>-<resumo>` → PR → CI verde → aprovação do coordenador → merge.

## Desenvolvimento assistido por IA

Este repositório foi estruturado para times usando Claude, Cursor, Codex,
Gemini etc. As instruções vivem em `AGENTS.md`; `CLAUDE.md`, `GEMINI.md` e
`.cursor/rules/` apenas apontam para ele. **Edite somente `AGENTS.md`.**

Princípio central: **a IA gera, o humano responde pelo código** —
nenhum PR sem revisão humana.
