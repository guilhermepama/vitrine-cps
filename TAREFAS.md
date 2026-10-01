# TAREFAS — divisão por responsável

Cada módulo tem **um** representante responsável. Regras:

- O responsável completa a spec do seu módulo (usando `specs/_template.md`)
  e só então gera código com a IA de sua preferência.
- Mudança que atravessa módulos (schema compartilhado, rotas de outro
  módulo) passa pelo coordenador antes.
- PR aprovado pelo coordenador antes do merge (guardrail 18).

| Módulo | Spec | Responsável | Turma | Status |
|---|---|---|---|---|
| Cadastro (edições/turmas/projetos) | `specs/01-cadastro.md` | — | — | aguardando |
| Vitrine pública | `specs/02-vitrine-publica.md` | — | — | aguardando |
| Credenciamento + votação | `specs/03-credenciamento-votacao.md` | — | — | spec pronta |
| Resultados/relatórios | `specs/04-resultados.md` | — | — | aguardando |
| Administração | `specs/05-admin.md` | — | — | aguardando |
| Coordenação, infra, revisão final | — | Guilherme Pama | DSM | ativo |

## Ordem sugerida de dependências

1. ~~ADR-002 (stack)~~ — aceita: Python + Django + PostgreSQL
2. Spec 01 (modelo de dados base: edições, turmas, projetos)
3. Specs 02 e 03 em paralelo (dependem do modelo da 01)
4. Specs 04 e 05 por último (dependem de dados existirem)

## Ferramentas de IA do time

Qualquer ferramenta serve, desde que leia as instruções do repositório:

- **Claude (Code/app)**: lê `CLAUDE.md` → `AGENTS.md` automaticamente.
- **Cursor**: lê `.cursor/rules/projeto.mdc` → `AGENTS.md`.
- **Codex e similares**: leem `AGENTS.md` direto.
- **Gemini CLI**: lê `GEMINI.md` → `AGENTS.md`.

Se a sua ferramenta não carregar nada disso sozinha, cole o conteúdo de
`AGENTS.md` + a spec da sua tarefa no início da conversa.
