# Vitrine CPS — Estado do projeto

> **Propósito**: snapshot de onde o projeto está. Leia este arquivo ANTES de
> retomar qualquer trabalho — humano ou IA. Mantido **só** pelo
> coordenador (Guilherme). Demais membros: status da tarefa vai na
> descrição do PR (evita conflito de merge neste arquivo).
>
> **Última atualização**: 2026-10-02 — Guilherme

## Fase atual

**Especificação → início do código.** Stack decidida (ADR-002: Python +
Django + PostgreSQL). Próximo passo: spec 01 e esqueleto do projeto.

**Evento: quinta, 2026-10-29.** Tudo abaixo é planejado de trás para frente
a partir dessa data.

## Cronograma

| Até | Entrega | Responsável |
|---|---|---|
| 05/10 | Frentes definidas (`TAREFAS.md`); spec 01 pronta; **esqueleto Django no `main` com CI verde** + template base | Guilherme |
| 06/10 | Specs 02 (vitrine) e 06 (banca) completas, via PR | Cleiton, Guilherme |
| 08/10 | Servidor decidido (ADR-006), domínio configurado e ambiente publicado | Guilherme |
| 10/10 | Guia do aluno para cadastro de projetos | Barbara |
| 12/10 | Cadastro (via admin) + vitrine pública funcionando | Guilherme, Cleiton |
| **13/10** | **Vitrine no ar**: projetos cadastrados, links começam a circular | todos |
| 20/10 | Texto LGPD aprovado pela coordenação | Guilherme (externo) |
| 20/10 | Credenciamento + votação completos (spec 03); texto LGPD provisório até a aprovação | Renan |
| 20/10 | Banca (spec 06): critérios e jurados cadastrados, ficha impressa pronta | Guilherme |
| 21/10 | **Pré-ensaio interno** (só o time): fluxo completo em celulares reais | todos |
| 22/10 | Roteiro do staff nas estações + ficha da banca com critérios publicados | Barbara |
| 24/10 | **Ensaio geral**: estações reais, celulares reais, votos de teste | todos |
| 27/10 | Resultados (spec 04) implementado e testado com dados do ensaio | Renan |
| 27/10 | **Congelamento**: só entram correções de bug | — |
| 28/10 | Backup do banco (`pg_dump`) | Guilherme |
| 29/10 | Evento | — |
| 29/10 | Backup ao encerrar a votação | Guilherme |
| 30/10 | Resultado oficial: nota composta 70% banca + 30% público (ADR-007) | Renan |

As entregas de código foram antecipadas; ensaio, congelamento e evento
não mudam. A folga ganha fica entre 21/10 e 27/10 para correções.

## Escopo desta edição (corte por prazo)

- **Entra**: cadastro pelo admin, vitrine pública, credenciamento + votação
  completos (com todos os guardrails), avaliação da banca, resultado por
  turma com nota composta.
- **Fica para a próxima edição**: painel admin próprio (usar o do Django),
  cadastro de projeto pelo próprio aluno (se não couber até 12/10, o admin
  cadastra), relatórios elaborados, login e tela de avaliação do jurado
  (nesta edição a banca usa ficha impressa digitada no admin — ADR-008).
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
- [x] Banco: Neon; imagens: Cloudflare R2 (ADR-006); servidor pendente

## Em andamento

- [x] Equipe e frentes definidas (`TAREFAS.md`): Guilherme, Renan,
      Cleiton; Barbara em documentação de apoio
- [ ] Spec 01 (modelo de dados base)
- [ ] Levantamento dos cursos da Etec (Guilherme) — período pode ser
      semestre **ou ano**; a spec 01 já deve prever os dois

## Turmas desta edição

Fatec: DSM 1º, 2º, 3º · GTUR 2º, 3º (5 turmas). Etec: a levantar.

## Riscos / atenção

- **Equipe de 3 pessoas**: sem folga de gente. Se uma frente travar,
  cortar escopo daquela frente antes de redistribuir.

- **Prazo**: 4 semanas, time aprendendo Django. Se 15/10 escorregar, a
  vitrine perde a função de divulgação — cortar escopo antes de atrasar.
- **Gargalo de revisão**: todo PR passa pelo coordenador. Revisar em até
  24h, principalmente entre 05/10 e 20/10. Limite de ~300 linhas por PR;
  agente faz a checagem mecânica (`/revisar-pr`), o coordenador roda o
  código e responde pela aprovação. Votação: leitura linha a linha.
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
- 2026-10-01 Guilherme: banco no Neon (ADR-006); Supabase descartado.
- 2026-10-01 Guilherme: imagens no Cloudflare R2 (ADR-006).
- 2026-10-02 Guilherme: equipe definida (Renan: votação e resultados; Cleiton: vitrine; Guilherme: fundação e banca; Barbara: docs de apoio).
- 2026-10-02 Guilherme: banca em ficha impressa digitada no admin (ADR-008); cronograma de código antecipado, pré-ensaio em 21/10.
