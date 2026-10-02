# TAREFAS — divisão por responsável

Equipe desta edição: **Guilherme** (coordenação), **Renan** e **Cleiton**.
Barbara atua na operação do evento e no ensaio (em horário de aula).

## Regras

- O responsável completa a spec da sua frente (`/nova-spec`, a partir de
  `specs/_template.md`), abre PR **só com a spec** e espera a aprovação
  antes de gerar código.
- **Cada frente é um app Django próprio** (`cadastro/`, `vitrine/`,
  `votacao/`, `banca/`, `resultados/`). Você e o seu agente só alteram a
  pasta do seu app. `settings.py`, `urls.py` raiz e os models do
  `cadastro` são do coordenador — precisou mudar, peça.
- **PR pequeno**: até ~300 linhas alteradas, sem contar migrations e
  testes. Maior que isso, fatie (ex: models → admin → telas).
- PR aprovado pelo coordenador antes do merge (guardrail 18). PRs do
  próprio coordenador entram com o CI verde (bypass, ADR-005) e análise
  do `/revisar-pr`; revisão por pares ainda a definir.
- Status da tarefa vai na **descrição do PR**. `docs/03-estado.md` é
  atualizado só pelo coordenador.
- Branch desatualizada com a `main` ("out-of-date") é normal depois de
  cada merge: clique em **Update branch** no PR.

## Frentes

| Frente | Specs | App | Responsável | GitHub | Entrega |
|---|---|---|---|---|---|
| Fundação: models, admin, importação da lista, moderação, esqueleto, infra, guia do representante | 00, 01 (absorve a 05) | `cadastro/` | Guilherme | @guilhermepama | 05–10/10 |
| Área do grupo (RA + link de edição) e vitrine pública | 02 | `vitrine/` | Cleiton | @gustimmolp | 10/10 e 12/10 |
| Credenciamento + votação | 03 | `votacao/` | Renan | @ReCroffi | 20/10 |
| Banca — sistema (ficha para imprimir, digitação, conferência) | 06 | `banca/` | Guilherme | @guilhermepama | 20/10 |
| Resultados (nota composta 70/30) | 04 | `resultados/` | Renan | @ReCroffi | 27/10 |
| Roteiro do staff (escrito no ensaio geral) | — | `docs/` | Barbara | (a confirmar) | 22/10 |
| Banca — operação (fichas no evento, digitação depois) | — | — | Barbara | — | 29 e 30/10 |

**Cadastro (ADR-009)**: as coordenações enviam a lista (projeto, turma,
representante, RA) na planilha modelo até 08/10; o coordenador importa;
o representante reivindica o projeto com o RA e edita pelo link secreto;
o coordenador aprova a publicação.

**Vitrine**: o coordenador entrega a identidade visual (cores, tipografia,
logo) junto com o esqueleto; a frente monta o template único.

**Votação**: não se divide entre pessoas — é o módulo de maior risco.
Revisão linha a linha.

**Barbara**: disponível em horário de aula e no evento. Roteiro do staff
escrito durante o ensaio geral (22/10); no dia 29 entrega e recolhe as
fichas dos jurados; em 30/10, em horário de aula, digita as notas no
admin (usuário com permissão só de digitação). A conferência das notas
é do coordenador.

## Ordem de dependências

1. ~~ADR-002 (stack)~~ — aceita: Python + Django + PostgreSQL
2. Spec 01 + esqueleto (fundação) — destrava todo o resto
3. Specs 02, 03 e 06 em paralelo (dependem do modelo da 01)
4. Spec 04 por último (depende de votos e notas da banca)

## Ferramentas de IA do time

Qualquer ferramenta serve, desde que leia as instruções do repositório:

- **Claude (Code/app)**: lê `CLAUDE.md` → `AGENTS.md` automaticamente.
- **Cursor**: lê `.cursor/rules/projeto.mdc` → `AGENTS.md`.
- **Codex e similares**: leem `AGENTS.md` direto.
- **Gemini CLI**: lê `GEMINI.md` → `AGENTS.md`.

Se a sua ferramenta não carregar nada disso sozinha, cole o conteúdo de
`AGENTS.md` + a spec da sua tarefa no início da conversa.

Agente rodando em servidor próprio segue as mesmas regras e usa a
credencial da conta GitHub do responsável (ver "Git — limites para
agentes" no `AGENTS.md`).
