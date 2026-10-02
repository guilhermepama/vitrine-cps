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
- **Um app Django por frente** (`cadastro/`, `vitrine/`, `votacao/`,
  `banca/`, `resultados/`). Altere só o app do seu responsável.
  `settings.py`, `urls.py` raiz e models do `cadastro` são do coordenador.
- **PR pequeno**: até ~300 linhas alteradas (sem contar migrations e
  testes). Passou disso, divida em PRs sequenciais.
- **Não edite `docs/03-estado.md`** — é do coordenador. O status da
  tarefa vai na descrição do PR.
- Commits pequenos e descritivos, em português:
  `modulo: o que mudou` (ex: `votacao: valida assinatura HMAC da janela`).
- Trabalhe em branch por tarefa (`feat/<modulo>-<resumo>`), PR para `main`.
  `main` protegida — nada de push direto.

## Git — limites para agentes

Valem para qualquer agente, rodando no seu computador ou num servidor.
A `main` é protegida pelo GitHub; **as branches dos colegas não** — por
isso estas regras.

- **Só a sua branch.** O agente trabalha na branch da tarefa do seu
  responsável. Nunca faz commit, push, rebase ou reset em branch de outra
  pessoa.
- **Nada de force-push em branch alheia** (`--force`, `--force-with-lease`).
- **Nunca apaga branch remota nem tag** (`git push --delete`, `git push :branch`).
  A branch é removida pelo GitHub no merge do PR.
- **Agente não faz merge nem aprova PR**, e não altera `.github/` (CI,
  rulesets, CODEOWNERS) nem configurações do repositório — isso é do
  coordenador.
- **Todo push tem nome.** O agente usa a credencial da conta GitHub do seu
  responsável (chave SSH ou token cadastrados na conta da pessoa). Nada de
  deploy key ou conta compartilhada — quem commitou responde pelo código
  (guardrail 19).
- **Comando destrutivo → pare e pergunte ao humano**: `reset --hard`,
  `clean -fd`, `push --delete`, `filter-repo`, reescrita de histórico.

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
