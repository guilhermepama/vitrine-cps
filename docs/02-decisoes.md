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
- Status: aceita
- Data: 2026-10-01
- Contexto: time de representantes de turmas DSM, desenvolvimento assistido
  por IA (Claude, Cursor e possivelmente outros), sistema recorrente que
  precisa ser mantido por turmas futuras. Critério dominante: manutenção
  por alunos semestre a semestre > performance. Prazo: evento em
  2026-10-29 (4 semanas). O PPC do DSM ensina Python (Algoritmos, 1º sem.)
  e Flask (Web II, 2º sem.); ninguém das turmas atuais estudou TypeScript.
- Decisão:
  - **Python 3.12 + Django 5.2 (LTS)**, renderização no servidor com
    templates do Django. Sem SPA, sem framework de front.
  - **PostgreSQL** em todos os ambientes que rodam testes ou produção
    (SQLite não reproduz a concorrência do voto — G4).
  - **Admin do Django** como painel administrativo (cadastro de edições,
    turmas, abertura/encerramento da votação — specs 01 e 05).
  - Bibliotecas permitidas: `django`, `psycopg[binary]`, `pytest`,
    `pytest-django`, `qrcode` (QR das estações), `Pillow` (upload de
    imagens, G14), `gunicorn` e `whitenoise` (deploy),
    `django-storages[s3]` (imagens no R2 — ADR-006). Qualquer outra
    exige proposta aqui.
  - Rate limit (G7) com o framework de cache do Django, sem lib extra.
  - Hospedagem: ADR-006 (banco: Neon). Requisitos:
    HTTPS, Postgres gerenciado com backup, **sem hibernação no dia do
    evento** (QR escaneado não pode esperar a aplicação "acordar").
- Consequências: Django escolhido no lugar de Flask, apesar de o time já
  conhecer Flask, porque impõe uma estrutura única (apps, models,
  migrations) — com vários alunos gerando código por IA, Flask viraria
  várias arquiteturas no mesmo repositório. O admin, as migrations (G16),
  o ORM parametrizado (G13), a validação de formulários (G12) e
  `transaction.atomic` + `UniqueConstraint` (G4) vêm prontos. Custo:
  curva de aprendizado das convenções do Django. TypeScript/Node
  descartado por ser linguagem nova para o time no prazo disponível.

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

## ADR-007 — Avaliação da banca e nota final composta
- Status: aceita (login de jurado substituído pela ADR-008 nesta edição)
- Data: 2026-10-01
- Contexto: além do voto do público, uma banca avalia os projetos, e o
  peso da banca deve ser maior. Os dois votos têm naturezas diferentes:
  o público vota sim/não em quantos projetos quiser (total depende do
  movimento do evento); a banca dá notas por critério. Multiplicar o voto
  da banca ("1 jurado = N votos") deixaria o peso real fora de controle.
- Decisão:
  - **Resultado oficial = nota composta por turma: 70% banca + 30%
    público.** Pesos ficam na configuração da edição e são **publicados
    antes do evento**; não mudam depois de aberta a votação.
  - **Banca**: cada jurado dá nota **0–10 por critério**. Critérios desta
    edição: impacto social, impacto ambiental e, a confirmar, impacto
    comercial. Critérios são **dados da edição** (cadastrados no admin),
    não código. Nota de banca do projeto = média dos critérios, calculada
    sobre a média dos jurados que o avaliaram (jurado não precisa avaliar
    todos os projetos).
  - **Normalização min-max dentro da turma, para as duas partes**:
    `b = (banca - menor banca da turma) / (maior - menor)` e
    `p = (votos - menor) / (maior - menor)`; se maior = menor, vale 1.
    `final = 0,7·b + 0,3·p`. Desempate: maior nota de banca, depois mais
    votos do público.
  - **Jurados têm login próprio** (usuário do Django, grupo "banca") e
    registram as notas no celular. Avaliação da banca é identificada e
    auditável — só o voto do público é anônimo. Plano B: ficha impressa
    com os mesmos critérios, digitada no admin.
- Consequências: normalizar a banca só por "nota ÷ 10" foi descartado.
  Bancas costumam dar notas próximas (ex: 6,5 a 8), enquanto os votos do
  público variam muito; sem min-max, o público dominaria o resultado
  mesmo com peso de 30%. Com min-max, os 70/30 são o peso real. Custo:
  turma com 2 projetos vira 0 ou 1 em cada parte (aceito). Novo módulo:
  spec 06 (avaliação da banca); a spec 04 passa a calcular a nota
  composta. Os critérios medem impacto, não execução técnica — escolha da
  coordenação.

## ADR-006 — Hospedagem (banco, servidor, imagens)
- Status: aceita parcialmente — banco e imagens decididos; servidor até 2026-10-08
- Data: 2026-10-01
- Contexto: requisitos da ADR-002 — HTTPS, Postgres gerenciado com backup,
  sem hibernação longa no dia do evento. Time de alunos não deve
  administrar servidor de banco (backup, atualização, segurança).
- Decisão:
  - **Banco: Neon (Postgres gerenciado, plano gratuito).** Só o banco —
    login, admin e API ficam com o Django. Conexão pelo `DATABASE_URL`.
    Um branch do Neon para produção; desenvolvimento usa Postgres local.
  - **Backup manual obrigatório**: `pg_dump` na véspera do evento, ao
    encerrar a votação e após publicar o resultado. O plano gratuito só
    permite voltar ~6 h no tempo — insuficiente como único backup.
  - **Servidor do Django**: a decidir (não pode hibernar por minutos).
  - **Imagens dos projetos: Cloudflare R2** (armazenamento compatível com
    S3, sem cobrança de tráfego de saída, 10 GB grátis). Integração via
    `django-storages[s3]` (inclui `boto3`). Plataformas de deploy apagam
    arquivos enviados a cada novo deploy — por isso armazenamento externo.
    - Credencial da aplicação com permissão **só de leitura/escrita
      naquele bucket** (nunca token de administrador da conta), em
      variáveis de ambiente (G3).
    - Imagens servidas por **domínio próprio** ligado ao bucket. O
      endereço padrão `*.r2.dev` tem limite de requisições e não é para
      produção. URLs assinadas descartadas: expiram e quebram a prévia do
      link no WhatsApp, que é o canal de divulgação da vitrine.
    - Requer cartão ou PayPal cadastrado na Cloudflare, mesmo no grátis.
- Consequências: Supabase descartado — duplicaria autenticação e API que o
  Django já oferece, pausa o projeto após 1 semana sem uso (o sistema é
  usado em ondas semestrais) e não tem backup no plano gratuito. O Neon
  "dorme" após 5 min sem acesso, mas acorda em cerca de 1 s — aceitável;
  no dia do evento o acesso é contínuo. Limites do plano gratuito
  (verificados em 2026-10-01): 1 GB por projeto, 100 CU-hora/mês.

## ADR-008 — Banca em ficha impressa nesta edição
- Status: aceita
- Data: 2026-10-02
- Contexto: a equipe de desenvolvimento ficou com 3 pessoas (Barbara
  passou para apoio em documentação) e o prazo é 29/10. A ADR-007 previa
  login de jurado e tela de avaliação no celular, com a ficha impressa
  como plano B.
- Decisão: o plano B vira o plano A. Jurados avaliam em **ficha impressa
  e assinada**; a equipe digita as notas no admin do Django. Jurado é um
  registro (nome, edição), não um usuário com login. Normalização, pesos
  e desempate da ADR-007 não mudam.
- Consequências: a spec 06 cai para models, admin e ficha para imprimir.
  Sem dependência de Wi-Fi para a banca no dia do evento. A auditoria
  passa a ser a ficha assinada + registro de quem digitou cada nota. Custo:
  digitação manual após a avaliação (risco de erro — conferir por amostra).
  Login e tela do jurado ficam para a próxima edição.
