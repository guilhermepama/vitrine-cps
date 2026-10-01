# Vitrine CPS — Instruções para agentes de IA

> Este arquivo é a **fonte única** de instruções para qualquer agente de IA
> (Claude, Cursor, Codex, Gemini etc.). `CLAUDE.md`, `GEMINI.md` e
> `.cursor/rules/` apenas apontam para cá. **Edite somente este arquivo.**

## Antes de qualquer tarefa

1. Leia `docs/03-estado.md` — onde o projeto está agora e o próximo passo.
2. Leia `docs/00-contexto.md` — o que é o sistema e por quê.
3. Leia `docs/01-guardrails.md` — regras inegociáveis de segurança e qualidade.
4. Leia a spec da sua tarefa em `specs/` — o escopo do que você vai fazer.
5. Consulte `docs/02-decisoes.md` antes de propor mudança de arquitetura.

## Fluxo de trabalho (spec-driven)

- **Nenhum código sem spec.** Toda tarefa nasce de um arquivo em `specs/`.
  Se a spec não existe ou está incompleta, a entrega é a spec — não o código.
- Implemente **somente** o que a spec pede. Ideias fora do escopo viram
  proposta em `docs/02-decisoes.md` (status: proposta), nunca código direto.
- Cada módulo tem um responsável (ver `TAREFAS.md`). Não altere arquivos de
  módulos de outros responsáveis sem combinar — mudanças transversais passam
  pelo coordenador (Guilherme).
- Commits pequenos e descritivos, em português:
  `modulo: o que mudou` (ex: `votacao: valida assinatura HMAC da janela`).
- Trabalhe em branch por tarefa (`feat/<modulo>-<resumo>`), PR para `main`.
  `main` protegida — nada de push direto.

## Procedimentos padrão (skills)

Os três procedimentos recorrentes do time estão em `.claude/skills/`:

- `.claude/skills/nova-spec/SKILL.md` — criar/completar a spec de um módulo
- `.claude/skills/implementar-spec/SKILL.md` — implementar a partir de spec pronta
- `.claude/skills/revisar-pr/SKILL.md` — revisar PR contra spec e guardrails

**Claude** carrega essas skills automaticamente (invoque por nome, ex:
`/nova-spec`). **Cursor, Codex, Gemini e outras ferramentas**: abra o
SKILL.md correspondente e siga os passos como checklist — é markdown comum.

## Convenções

- **Idioma**: documentação, specs, commits e mensagens de UI em pt-BR.
  Código (variáveis, funções, tabelas) em inglês.
- **Stack**: definida em `docs/02-decisoes.md` (ADR-002). Não introduza
  bibliotecas fora das listadas lá sem registrar decisão.
- Variáveis de ambiente documentadas em `.env.example` — **nunca** commitar
  `.env` real, segredos ou o segredo HMAC.

## Resumo do sistema (detalhe em docs/00-contexto.md)

Plataforma da mostra semestral de projetos FATEC Olímpia + Etec:
cadastro de projetos por edição/turma → página pública de vitrine (divulga,
**não vota**) → votação presencial no evento via token único obtido por QR
dinâmico nas estações de credenciamento → relatório por categoria.

Regras que nenhuma implementação pode violar: ver `docs/01-guardrails.md`.
