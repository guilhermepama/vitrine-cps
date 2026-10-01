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
