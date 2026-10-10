# Vitrine CPS — Estado do projeto

> **Propósito**: snapshot de onde o projeto está. Leia este arquivo ANTES de
> retomar qualquer trabalho — humano ou IA. Mantido **só** pelo
> coordenador (Guilherme). Demais membros: status da tarefa vai na
> descrição do PR (evita conflito de merge neste arquivo).
>
> **Última atualização**: 2026-10-06 — Guilherme

## Fase atual

**Votação, banca e resultados na `main`; vitrine em revisão.** Specs 03
(F1–F8), 04 (fatias 1–3) e 06 (fatias 1–5) estão implementadas e com CI
verde (`d93b242`, 970 testes). Em 05/10, com o Renan ausente, o
coordenador fechou as frentes dele (ajustes dos pareceres #40–#43 e a
spec 04 inteira) — esses PRs entraram **sem a aprovação da ADR-010** e
ficam para a revisão posterior do Renan (ver "Em andamento"). Spec 02
(Cleiton) está nos PRs encadeados #44 → #45 → #46 → #47, aguardando
revisão do coordenador. Falta o cadastro 3/3 (admin e moderação), que
trava o cadastro aberto de 10/10.

**Evento: quinta, 2026-10-29.** Tudo abaixo é planejado de trás para frente
a partir dessa data.

## Cronograma

| Até | Entrega | Responsável |
|---|---|---|
| 05/10 | Frentes definidas (`TAREFAS.md`); spec 01 pronta; **esqueleto Django no `main` com CI verde** + identidade visual | Guilherme |
| 05/10 | Planilha modelo enviada às coordenações (ADR-009) | Guilherme |
| 06/10 | Specs 02 (vitrine + área do grupo) e 06 (banca) completas, via PR | Cleiton, Guilherme |
| 08/10 | Listas das coordenações recebidas (projeto, turma, representante, RA) | Guilherme (externo) |
| 08/10 | Servidor decidido (ADR-006), domínio configurado e ambiente publicado | Guilherme |
| 09/10 | Models + importação da lista + moderação no admin | Guilherme |
| **10/10** | **Cadastro aberto**: área do grupo no ar + guia do representante enviado | Cleiton, Guilherme |
| 12/10 | Vitrine pública funcionando; primeiros projetos aprovados | Cleiton, Guilherme |
| **13/10** | **Vitrine no ar**: links começam a circular | todos |
| 20/10 | Texto LGPD aprovado pela coordenação | Guilherme (externo) |
| 20/10 | Credenciamento + votação completos (spec 03); texto LGPD provisório até a aprovação | Renan |
| 20/10 | Banca (spec 06): critérios, jurados, ficha impressa e usuário de digitação | Guilherme |
| 21/10 | **Pré-ensaio interno** (só o time): fluxo completo em celulares reais | todos |
| **22/10** | **Ensaio geral** (quinta, horário de aula): estações reais, votos de teste, digitação de fichas de teste | todos |
| 22/10 | Roteiro do staff, a partir do ensaio | Barbara |
| 27/10 | Resultados (spec 04) implementado e testado com dados do ensaio | Renan |
| 27/10 | **Congelamento**: só entram correções de bug | — |
| 28/10 | Backup do banco (`pg_dump`) | Guilherme |
| 29/10 | Evento; fichas da banca recolhidas e guardadas com o coordenador | Barbara, Guilherme |
| 29/10 | Backup ao encerrar a votação | Guilherme |
| 30/10 | Digitação das notas da banca, em horário de aula | Barbara |
| 30/10 | Conferência por amostra contra as fichas + backup | Guilherme |
| 30/10 | Resultado oficial (à noite, ou na data definida pela coordenação): nota composta 70% banca + 30% público (ADR-007) | Renan, Guilherme |

As entregas de código foram antecipadas; ensaio, congelamento e evento
não mudam. Ensaio geral em 22/10 (quinta, mesmo dia da semana do evento,
em horário de aula). A folga fica entre 23/10 e 27/10 para correções.

## Escopo desta edição (corte por prazo)

- **Entra**: cadastro pelo próprio grupo a partir da lista das coordenações
  (RA + link de edição, com aprovação — ADR-009), vitrine pública,
  credenciamento + votação completos (com todos os guardrails), avaliação
  da banca em ficha impressa (ADR-008), resultado por turma com nota
  composta.
- **Fica para a próxima edição**: painel admin próprio (usar o do Django),
  login de aluno e envio de link por e-mail, relatórios elaborados, login
  e tela de avaliação do jurado.
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
- [x] Banco: Neon; imagens: Cloudflare R2; servidor: VPS com Coolify
      (ADR-006) — falta publicar
- [x] Esqueleto Django na `main` com CI verde (spec 00, PR #15)
- [x] Planilha modelo enviada às coordenações (02/10, sem coluna de turno)
- [x] Spec 01 completa, absorvendo a 05 (PR #16); models do cadastro com
      travas após abrir a votação (PR #17)
- [x] Spec 03 pronta para implementar, com rate limit (PR #18)
- [x] Spec 04 em rascunho, aguardando a spec 06 (PR #14)
- [x] Cadastro 2/3: importação da lista, slug imutável (PR #19)
- [x] `ip_do_cliente`/`chave_ip` compartilhados (#25); segredos da votação
      obrigatórios (#24); filtro de log P2 ligado (#26, #27)
- [x] ADR-010: aprovação em pares nos PRs do coordenador (#28, #29)
- [x] Servidor decidido: VPS com Coolify, IP real por `CF-Connecting-IP`
      (ADR-006, #30); `URL_PUBLICA` obrigatória em produção (#32)
- [x] **Spec 03 implementada (Renan)**: F1 models (#21), F2 abrir/encerrar
      e estações (#22), F3 QR e página da estação (#31), F4 emissão em
      `/entrar` com rate limit (#34), F5 cadastro do visitante (#33),
      F5b rate limit do cadastro (#35), F6 cédula e voto (#36), F7 filtro
      P2 (#26), F8 `medir_voto` e teste ponta a ponta (#37); ajustes dos
      pareceres (#40–#43)
- [x] Spec 02 completa (Cleiton, #23); spec 06 completa (#49); spec 04
      pronta com o formato da banca (#50)
- [x] **Spec 06 implementada**: models e `nota_banca_por_projeto` (#51),
      admin de critérios e jurados (#53), digitação em dois passos (#55),
      ficha para imprimir (#56), conferência e reabrir digitação (#58)
- [x] **Spec 04 implementada**: cálculo puro (#52), ranking com
      participação e permissões (#54), operacional e export (#57)
- [x] Config: `MAX_ENTRIES` do cache, filtro do token de edição no log,
      `base.html` mínimo (#38, #39); imagens sem metadados (#48)

## Em andamento

- [ ] **Revisão posterior da ADR-010 (Renan, até 07/10)**: PRs do
      coordenador mergeados em 05–06/10 sem aprovação — #38, #39, #40,
      #41, #42, #43, #48, #49, #50, #51, #52, #53, #54, #55, #56, #57,
      #58. Prioridade: #40–#43 (votação, commit por commit — roteiro no
      #40), depois #52/#54/#57 (resultados) e #51–#58 (banca). Violação
      de guardrail → correção antes do próximo merge do coordenador.
- [ ] Marcador `Merge sem aprovação (ADR-010): …` nas descrições desses
      PRs (coordenador)
- [ ] Revisão dos PRs #44 → #45 → #46 → #47 (spec 02, Cleiton) — nessa
      ordem; o #47 depende também do #39 (já na `main`)
- [ ] **Cadastro 3/3** (admin: moderação em lote, formsets, regerar/
      revogar link, pesos só leitura) — trava o cadastro aberto de 10/10
- [ ] Identidade visual (`static/css/base.css` ainda não está no repo)
- [ ] Publicar o ambiente no VPS (Coolify) e confirmar o cabeçalho do IP
      real — até 08/10
- [ ] Listas das coordenações (até 08/10)
- [ ] Votação em ensaio/deploy só depois do `/como-votar/` (#44) entrar
- [ ] Pré-ensaio 21/10: `medir_voto` na edição "Pré-ensaio", voto real
      pelo domínio e pelo proxy; medir o teto de 300/10 min por IP
- [ ] Coordenação: regra para alunos da Etec menores em página pública
- [ ] Levantamento dos cursos e turnos da Etec (Guilherme)
- [ ] Texto LGPD final (coordenação, 20/10)

## Turmas desta edição

Fatec: DSM 1º, 2º, 3º · GTUR 2º, 3º (5 turmas). Etec: a levantar.

## Riscos / atenção

- **Listas das coordenações (ADR-009)**: dependência externa até 08/10.
  Turma sem lista no prazo é cadastrada pelo admin (plano B).
- **Equipe de 3 pessoas**: sem folga de gente. Se uma frente travar,
  cortar escopo daquela frente antes de redistribuir.

- **Prazo**: 4 semanas, time aprendendo Django. Se 15/10 escorregar, a
  vitrine perde a função de divulgação — cortar escopo antes de atrasar.
- **Gargalo de revisão**: todo PR passa pelo coordenador. Revisar em até
  24h, principalmente entre 05/10 e 20/10. Limite de ~300 linhas por PR;
  agente faz a checagem mecânica (`/revisar-pr`), o coordenador roda o
  código e responde pela aprovação. Votação: leitura linha a linha.
- **Revisão dos PRs do coordenador (ADR-010)**: 17 PRs entraram em
  05–06/10 sem a aprovação do Renan e sem o marcador. A revisão posterior
  é o que valida esse código; enquanto não acontecer, nada dele vai para
  ensaio. Daqui em diante, voltar ao fluxo normal: parecer → aprovação →
  merge.
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
- 2026-10-02 Guilherme: cadastro pelo grupo volta ao escopo — lista das coordenações + RA + link de edição + aprovação (ADR-009).
- 2026-10-02 Guilherme: ensaio geral movido para 22/10 (horário de aula); Barbara na operação da banca no evento e no roteiro do staff.
- 2026-10-02 Guilherme: notas da banca digitadas depois do evento (30/10, em aula); resultado oficial após a conferência.
- 2026-10-02 Guilherme: esqueleto Django na main (#15); Neon: projeto vitrine-cps só produção, dev em vitrine-dev por pessoa.
- 2026-10-02 Guilherme: specs 01 (#16), 03 (#18) e 04 (#14) na main; models do cadastro com travas após abrir a votação (#17).
- 2026-10-02 Guilherme: abertura/encerramento da votação viraram campos da Edicao (sem config_votacao); ensaio de 22/10 é edição separada.
- 2026-10-02 Guilherme: ADR-003 complementada — consentimento truncado para a hora, id UUID, sem log nas rotas do visitante.
- 2026-10-03 Guilherme: PRs do coordenador passam a ter a aprovação do Renan (ADR-010, #28).
- 2026-10-05 Guilherme: Renan ausente; coordenador fechou votação (ajustes #40–#43) e resultados (#52, #54, #57) e a banca (#51–#58).
- 2026-10-06 Guilherme: Renan de volta; specs 03, 04 e 06 na `main` com CI verde; pendente a revisão posterior da ADR-010 e o cadastro 3/3.
