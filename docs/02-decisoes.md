# Registro de decisões (ADR-lite)

Toda decisão de arquitetura relevante vira uma entrada aqui, numerada, com
contexto e consequência. Agentes de IA: **consultem antes de propor mudanças**;
propostas novas entram com status `proposta` e só viram `aceita` pelo
coordenador.

Formato:

```
## ADR-NNN — Título
- Status: aceita | proposta | substituída por ADR-XXX
- Data: AAAA-MM-DD
- Contexto: qual problema estava em jogo
- Decisão: o que foi decidido
- Consequências: o que isso implica / o que foi descartado
```

---

## ADR-001 — Unicidade de voto por token físico-presencial
- Status: aceita
- Data: 2026-10-01
- Contexto: garantir 1 voto por pessoa por projeto sem cadastro do eleitor.
  Um link simples permitiria votos ilimitados; geolocalização não garante
  unicidade e é falsificável.
- Decisão: token UUID emitido sob demanda no scan de QR dinâmico em estações
  de credenciamento supervisionadas. URL do QR assinada (HMAC) com janela
  por estação que expira a cada rotação (30–60s). Token válido até o fim da
  votação. 1 token = máx. 1 voto por projeto; voto livre em quantos projetos
  quiser. Idempotência por cookie httpOnly. Rate limit por IP (generoso) e
  por janela de estação.
- Consequências: pessoa com múltiplos aparelhos obtém múltiplos tokens —
  limitação aceita; backstop é o staff nas estações. Descartados:
  geolocalização, tokens pré-impressos, cadastro com CPF.

## ADR-002 — Stack de implementação
- Status: proposta (DECIDIR ANTES DE DISTRIBUIR TAREFAS DE CÓDIGO)
- Data: —
- Contexto: time de representantes de turmas DSM, desenvolvimento assistido
  por IA (Claude, Cursor e possivelmente outros), sistema recorrente que
  precisa ser mantido por turmas futuras. Critério dominante: manutenção
  por alunos semestre a semestre > performance.
- Decisão: (pendente)
- Consequências: nenhuma spec de código deve fixar linguagem/framework até
  esta ADR ser aceita.

## ADR-003 — Captação de visitantes desacoplada do voto
- Status: aceita
- Data: 2026-10-01
- Contexto: coordenação quer contatos (nome, email, telefone) para
  comunicações futuras; voto deve permanecer anônimo; CPF descartado por
  sensibilidade desproporcional à finalidade.
- Decisão: formulário pós-scan no celular do eleitor, obrigatório
  (nome + email) para liberar a cédula, telefone opcional, com checkbox de
  consentimento LGPD. Gravação na tabela `visitantes` sem qualquer vínculo
  com token ou voto.
- Consequências: não é possível auditar "quem votou em quem" — por design.
  Métricas cruzadas (ex: taxa de conversão cadastro→voto) só em agregado.

## ADR-004 — CI e proteção da `main`
- Status: aceita (regra de aprovação ajustada pela ADR-005)
- Data: 2026-10-01
- Contexto: time grande de representantes, código gerado por IA e stack
  ainda indefinida. Os guardrails precisam de uma barreira automática
  antes da revisão humana, e essa barreira não pode depender da ADR-002.
- Decisão: workflow `.github/workflows/ci.yml` com 4 checks obrigatórios
  na `main` (rulesets em `.github/rulesets/` — ver ADR-005):
  `guardrails` (verificador heurístico de G3, G6, G9, G13 — com testes do
  próprio verificador), `segredos` (gitleaks no histórico), `testes`
  (detecta a stack; sem código só informa, com código exige testes
  passando) e `convencoes-pr` (título `modulo: ...`, spec citada no PR com
  código, G20). Merge só por PR com 1 aprovação, squash, histórico linear,
  conversas resolvidas, aprovação descartada a cada novo push.
  `CODEOWNERS` exige o coordenador em `.github/`, guardrails, decisões e
  instruções de agentes — um PR roda a própria versão do workflow, então o
  CI sozinho não impede alguém de afrouxá-lo.
- Consequências: o verificador é heurístico (pega o erro óbvio, não o
  sutil) — a revisão humana continua obrigatória (G18). Ao aceitar a
  ADR-002, ajustar o job `testes` e o `dependabot.yml` para a stack.
  Renomear job do CI exige atualizar o ruleset.

## ADR-005 — Coordenador aprova todos os PRs, inclusive os próprios
- Status: aceita
- Data: 2026-10-01
- Contexto: o coordenador quer ser o ponto único de aprovação. O GitHub
  não deixa o autor aprovar o próprio PR, e a redação original do G18
  ("revisado por outra pessoa") travaria os PRs do coordenador.
- Decisão: dois rulesets na `main`. `main-checks` (sem exceção para
  ninguém): só via PR, squash, histórico linear, conversas resolvidas e os
  4 checks do CI verdes. `main-aprovacao`: 1 aprovação de code owner,
  descartada a cada novo push; o papel admin tem bypass só no modo PR.
  `CODEOWNERS` = `* @guilhermepama` — aprovação entre alunos não basta.
  G18 reescrito.
- Consequências: os PRs do coordenador não têm segundo olhar humano —
  o CI e a skill `revisar-pr` viram a única revisão deles; para PRs que
  tocam votação/guardrails, pedir revisão opcional a um representante é
  recomendado. Todo PR de aluno passa por uma pessoa só: gargalo perto do
  evento. Se o coordenador sair, um novo admin precisa assumir o
  `CODEOWNERS`, senão nenhum PR de aluno é mergeável.
