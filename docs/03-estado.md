# Vitrine CPS — Estado do projeto

> **Propósito**: snapshot de onde o projeto está. Leia este arquivo ANTES de
> retomar qualquer trabalho — humano ou IA. Mantido pelo coordenador
> (Guilherme); demais membros escrevem apenas no "Registro rápido" (append).
>
> **Última atualização**: 2026-10-01 — Guilherme

## Fase atual

**Especificação → início do código.** Stack decidida (ADR-002: Python +
Django + PostgreSQL). Próximo passo: spec 01 e esqueleto do projeto.

**Evento: quinta, 2026-10-29.** Tudo abaixo é planejado de trás para frente
a partir dessa data.

## Cronograma

| Até | Entrega | Responsável |
|---|---|---|
| 05/10 | Representantes com conta no GitHub; módulos distribuídos (`TAREFAS.md`); spec 01 pronta | Guilherme |
| 07/10 | Esqueleto Django no `main` com CI verde (testes rodando de verdade) | Guilherme |
| 08/10 | Hospedagem decidida (ADR-006) e ambiente publicado | Guilherme |
| 14/10 | Cadastro (via admin) + vitrine pública funcionando | módulos 01, 02 |
| **15/10** | **Vitrine no ar**: alunos cadastram projetos, links começam a circular | todos |
| 20/10 | Texto LGPD aprovado pela coordenação | Guilherme (externo) |
| 23/10 | Credenciamento + votação completos (spec 03) | módulo 03 |
| 23/10 | Avaliação da banca (spec 06) + critérios e jurados cadastrados | módulo 06 |
| 24/10 | **Ensaio geral**: estações reais, celulares reais, votos de teste | todos |
| 27/10 | **Congelamento**: só entram correções de bug | — |
| 29/10 | Evento | — |
| 30/10 | Resultado oficial: nota composta 70% banca + 30% público (ADR-007) | módulo 04 |

## Escopo desta edição (corte por prazo)

- **Entra**: cadastro pelo admin, vitrine pública, credenciamento + votação
  completos (com todos os guardrails), avaliação da banca, resultado por
  turma com nota composta.
- **Fica para a próxima edição**: painel admin próprio (usar o do Django),
  cadastro de projeto pelo próprio aluno (se não couber até 14/10, o admin
  cadastra), relatórios elaborados.
- A votação (spec 03) **não é dividida** entre várias pessoas — é o módulo
  de maior risco.

## Feito

- [x] Arquitetura de votação definida e registrada (ADR-001)
- [x] Captação de visitantes definida (ADR-003): desacoplada do voto, LGPD
- [x] Contexto completo em `docs/00-contexto.md`
- [x] Guardrails publicados em `docs/01-guardrails.md`
- [x] Spec 03 (credenciamento/votação) completa — padrão para as demais
- [x] Repositório público no GitHub, CI com 4 checks e `main` protegida
      (ADR-004, ADR-005 — coordenador aprova todos os PRs)
- [x] Referência dos cursos para a modelagem (`docs/referencias/cursos.md`)
- [x] Stack decidida (ADR-002)

## Em andamento

- [ ] Contas GitHub dos representantes + `TAREFAS.md`
- [ ] Spec 01 (modelo de dados base)
- [ ] Levantamento dos cursos da Etec (Guilherme) — período pode ser
      semestre **ou ano**; a spec 01 já deve prever os dois

## Turmas desta edição

Fatec: DSM 1º, 2º, 3º · GTUR 2º, 3º (5 turmas). Etec: a levantar.

## Riscos / atenção

- **Prazo**: 4 semanas, time aprendendo Django. Se 15/10 escorregar, a
  vitrine perde a função de divulgação — cortar escopo antes de atrasar.
- **Gargalo de revisão**: todo PR passa pelo coordenador. Revisar em até
  24h, principalmente entre 07/10 e 23/10.
- Pesos e critérios da banca precisam ser **divulgados antes do evento**
  (ADR-007). Confirmar com a coordenação se "impacto comercial" entra.
- Texto do consentimento LGPD depende da coordenação (fora do nosso controle)
  e bloqueia o formulário de visitante.
- Hospedagem com hibernação (plano gratuito que "dorme") quebra o QR no dia
  do evento — requisito na ADR-002.

## Registro rápido (append-only — qualquer membro)

Formato: `- AAAA-MM-DD <nome>: <nota curta>`

- 2026-10-01 Guilherme: repositório criado e estruturado.
- 2026-10-01 Guilherme: CI (guardrails, segredos, testes, convenções de PR) e ruleset da main.
- 2026-10-01 Guilherme: stack decidida (Python + Django + Postgres); evento em 29/10.
- 2026-10-01 Guilherme: banca com peso 70% (ADR-007); critérios: impacto social, ambiental e talvez comercial.
