# Vitrine CPS — Estado do projeto

> **Propósito**: snapshot de onde o projeto está. Leia este arquivo ANTES de
> retomar qualquer trabalho — humano ou IA. Mantido pelo coordenador
> (Guilherme); demais membros escrevem apenas no "Registro rápido" (append).
>
> **Última atualização**: 2026-10-01 — Guilherme

## Fase atual

**Especificação** — nenhum código ainda (bloqueado pela ADR-002, de propósito).

## Feito

- [x] Arquitetura de votação definida e registrada (ADR-001): QR dinâmico
      assinado por estação, token sob demanda, voto livre 1×/projeto
- [x] Captação de visitantes definida (ADR-003): desacoplada do voto, LGPD
- [x] Contexto completo em `docs/00-contexto.md`
- [x] Guardrails publicados em `docs/01-guardrails.md`
- [x] Spec 03 (credenciamento/votação) completa — padrão para as demais
- [x] Esqueleto do repositório no GitHub
- [x] CI + proteção da `main` (ADR-004) — ruleset a importar nas configurações do GitHub

## Em andamento

- [ ] Decisão de stack (ADR-002) — **bloqueia toda tarefa de código**
- [ ] Definir responsáveis por módulo em `TAREFAS.md`

## Próximos passos (ordem)

1. Fechar ADR-002 (stack) — critério: manutenção por turmas futuras
2. Reunião com representantes: distribuir módulos (`TAREFAS.md`)
3. Responsáveis completam specs 01, 02, 04, 05
4. Início do código: spec 01 primeiro (modelo de dados base)

## Riscos / atenção

- Stack indefinida + time ansioso = cada um começa numa linguagem. Não
  liberar tarefas de código antes da ADR-002.
- Texto do consentimento LGPD depende da coordenação (fora do nosso controle).
- Data do evento ainda não registrada aqui — definir e trabalhar de trás
  para frente no cronograma.

## Registro rápido (append-only — qualquer membro)

Formato: `- AAAA-MM-DD <nome>: <nota curta>`

- 2026-10-01 Guilherme: repositório criado e estruturado.
- 2026-10-01 Guilherme: CI (guardrails, segredos, testes, convenções de PR) e ruleset da main.
