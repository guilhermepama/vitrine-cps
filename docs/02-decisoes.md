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
    `django-storages[s3]` (imagens no R2 — ADR-006), `dj-database-url`
    (lê o `DATABASE_URL`; incluída em 2026-10-02 no esqueleto — parser
    próprio seria código a manter sem ganho). Qualquer outra exige
    proposta aqui.
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
- Complemento (2026-10-02, PRs #14 e #18): sem coluna de vínculo, ainda dá
  para cruzar visitante e token **pelo horário** — o cadastro é gravado
  segundos depois da emissão do token. Por isso:
  - `visitantes.consentimento_em` é gravado **truncado para a hora**
    (minutos e segundos zerados). O G10 pede data e hora do aceite, não
    segundos. O CSV de visitantes sai só com a data (spec 04).
  - `visitantes.id` é UUID (sem sequência que revele a ordem de cadastro)
    e as rotas do visitante não escrevem linha de log por request (spec 03,
    "Correlação visitante × token").
  - O visitante recebe `edicao_id` direto da edição em votação, nunca do
    token (G6).
  - Recomendado na aprovação do #18, para a implementação da spec 03: a
    chave do rate limit por IP vai para o cache como hash com segredo, não
    o IP em claro (a tabela do cache entra no `pg_dump`).
  - **Limite aceito**: numa hora com poucos cadastros (início e fim do
    evento) o grupo de visitantes é pequeno e a inferência fica mais
    fácil; quem tem o banco inteiro vê a ordem física das linhas. O
    controle que resta é o acesso restrito ao banco e aos dumps (ADR-006).
    O sistema não promete anonimato absoluto contra quem tem o banco.

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
- Status: aceita (PRs do coordenador ajustados pela ADR-010)
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
- Status: aceita — banco e imagens em 2026-10-01; servidor em 2026-10-03
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
  - **Servidor do Django: VPS do coordenador (Hostinger, no Brasil),
    com Coolify.** Não hiberna (ADR-002) e fica na mesma região do Neon
    (São Paulo): a transação do voto faz várias consultas com a `Edicao`
    travada e não pode pagar latência entre continentes.
    - **Proxy**: o Traefik do Coolify termina o HTTPS (Let's Encrypt) e
      preenche `X-Forwarded-Proto` (`SECURE_PROXY_SSL_HEADER`). Aceita
      corpo de **pelo menos 4 MB por requisição** — uma imagem de até
      3 MB mais o formulário (spec 02); o Traefik não limita o corpo por
      padrão.
    - **Sem log de acesso**: gunicorn sem `--access-logfile` e access log
      do Traefik desligado (o padrão). Atende o P2 da spec 03 (rotas do
      visitante) e a spec 02 (`/grupo/editar/<token>/`, com o token na
      URL). Do container só sai o log da aplicação, que passa pelo filtro
      `votacao/logs.py`.
    - **IP real: `DJANGO_IP_HEADER=X-Real-Ip`.** O Traefik descarta esse
      cabeçalho quando vem do cliente e o preenche com o IP de quem abriu
      a conexão. Para isso valer, o domínio do app fica **só no DNS da
      Cloudflare, sem o proxy** ("nuvem cinza"): com o proxy, o IP visto
      seria o da Cloudflare e o rate limit por IP viraria um contador
      único para todo mundo. **Teste obrigatório ao publicar**: requisição
      com `X-Real-Ip` e `X-Forwarded-For` falsos → `ip_do_cliente` não
      devolve o valor falso.
    - **Deploy**: o Coolify publica a `main` pelo app do GitHub (só
      leitura). `collectstatic` no build; início com
      `python manage.py migrate --noinput && gunicorn config.wsgi --bind 0.0.0.0:8000 --workers 3`
      (G16). Um container só: com mais de um, o `migrate` do início
      disputaria.
    - **O banco continua no Neon** — o Coolify não cria Postgres no VPS.
    - Variáveis de ambiente só no painel do Coolify, nunca no repositório
      (G3).
    - Limite de memória no container, para os outros serviços do VPS não
      disputarem recursos com a votação na noite do evento.
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
  (verificados em 2026-10-02): 0,5 GB por projeto (exibido na criação do
  projeto), 100 CU-hora/mês **por projeto, somando todos os branches** —
  esgotou, o banco fica suspenso até o mês seguinte. Por isso o projeto
  `vitrine-cps` é só produção; desenvolvimento usa projeto separado
  (`vitrine-dev`) ou Postgres local.
  - Pendente: o projeto está na conta pessoal do coordenador. Para o
    sistema sobreviver às turmas, transferir para uma organização do Neon
    com mais de um administrador.
  - **Servidor**: plataformas gratuitas de deploy descartadas — hibernam
    ou exigem plano pago para não hibernar. O VPS é **compartilhado** com
    outros serviços do coordenador: se um deles for comprometido, os
    segredos deste também ficam expostos. Aceito nesta edição, com SSH só
    por chave e o painel do Coolify só com o coordenador. O time não
    administra o servidor; deploy só pela `main`, via PR aprovado. Mesma
    pendência do Neon: servidor na conta pessoal do coordenador — para as
    próximas edições, levar para uma infraestrutura com mais de um
    administrador.

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
  Digitação feita no dia seguinte ao evento (30/10), em horário de aula;
  o resultado oficial sai depois da conferência.
  Login e tela do jurado ficam para a próxima edição.

## ADR-009 — Cadastro do projeto pelo próprio grupo (RA + link de edição)
- Status: aceita
- Data: 2026-10-02
- Contexto: são no mínimo 5 turmas com vários projetos cada. Cadastrar
  todos pelo admin concentraria o trabalho na equipe e viraria gargalo
  entre 10 e 13/10. O escopo original deixava o cadastro pelo aluno para
  a próxima edição. Sistema de contas (login, senha, recuperação) não
  cabe no prazo.
- Decisão:
  - **Lista prévia das coordenações**: cada coordenação de curso envia,
    em planilha modelo, projeto, turma, nome do representante e RA. O
    admin importa a lista; os projetos nascem como `pre_cadastrado`.
    Isso elimina duplicidade e cadastro de terceiros.
  - **RA reivindica, link secreto edita**: o representante informa o RA
    uma única vez; o sistema mostra o **link de edição exclusivo** do
    projeto (token aleatório). A partir daí o RA não abre mais nada —
    RA não é senha (colegas conhecem o RA uns dos outros). Link perdido
    ou reivindicação indevida: o admin gera um novo link e o anterior
    deixa de valer.
  - **RA nunca é guardado em claro**: só HMAC-SHA256 do RA com segredo em
    variável de ambiente. O token de edição também é guardado como hash.
    RA nunca aparece em página pública nem em log.
  - **Moderação**: nada é público sem aprovação. Fluxo de status:
    `pre_cadastrado` → `em_revisao` → `publicado` (ou `ajustes`, volta ao
    grupo). Admin aprova em lote.
  - **Prazo de edição** por edição; depois dele o link de edição só mostra
    o conteúdo. Projeto publicado vira conteúdo fixo após o evento.
  - Plano B: turma cuja lista não chegar até 08/10 é cadastrada pelo admin.
- Consequências: o trabalho manual da equipe cai para importar listas e
  aprovar. Dependência externa: listas das coordenações até 08/10, no
  formato da planilha modelo. Verificação de RA precisa de rate limit e
  resposta genérica (RAs são sequenciais e enumeráveis). Envio do link
  por e-mail e login de aluno ficam para a próxima edição. Pendente com a
  coordenação: regra para alunos da Etec menores de idade em página
  pública (até decidir: equipe só com primeiro nome e sem fotos de
  pessoas, apenas do projeto). O RA do representante não é dado de
  visitante — os guardrails 9–11 continuam valendo para visitantes.

## ADR-010 — Aprovação em pares nos PRs do coordenador
- Status: aceita
- Data: 2026-10-03
- Contexto: pela ADR-005, os PRs do coordenador entravam pelo bypass sem
  segundo olhar humano — só CI e `/revisar-pr`. Esses PRs tocam as partes
  mais sensíveis (`settings.py`, models do `cadastro`, guardrails,
  decisões), e a revisão opcional não aconteceu na prática.
- Decisão:
  - **PR do coordenador só entra com a aprovação do Renan Croffi
    (@ReCroffi)**, pedida como revisor no próprio PR. Com a aprovação e os
    checks verdes, o coordenador faz o merge pelo bypass.
  - **Ordem do fluxo (vale para todo PR):** CI verde → parecer do
    `/revisar-pr` no PR → atualizar com a `main`, se preciso → aprovação
    humana → squash. Atualizar antes de aprovar: o ruleset descarta a
    aprovação a cada push.
  - **O que o GitHub não impõe e vale por combinado:**
    - "Request changes" do Renan = não fazer merge, salvo pela exceção.
    - Conversa aberta pelo Renan só ele resolve.
    - Nova aprovação: "Update branch" sem conflito não pede; conflito ou
      mudança de conteúdo pede.
    - Aprovação do Renan diz o que ele conferiu; quando não conseguir ler,
      ele deixa Comment, não Approve.
  - **Exceção — merge sem a aprovação.** Quem decide é o coordenador,
    avisando no PR. Vale só em dois casos:
    - **sem resposta**: 24h depois do pedido de revisão (12h de 18/10 a
      29/10) e o PR trava outro trabalho;
    - **correção urgente**: produção fora do ar, ensaio ou evento travado,
      ou falha de segurança/LGPD.
    **Não vale** para PR que muda guardrails, ADRs ou o processo de
    aprovação — esses sempre esperam o Renan.
  - **Registro e revisão posterior.** O motivo vai na descrição do PR,
    antes do merge, com o marcador fixo `Merge sem aprovação (ADR-010): …`.
    O Renan revisa em até 48h depois do merge e sempre antes do próximo
    marco. Violação de guardrail encontrada → revert ou correção antes do
    próximo merge do coordenador, e a correção passa pelo Renan.
  - **PRs dos alunos não mudam** (ADR-005): continuam exigindo a
    aprovação do coordenador. O Renan aprova os PRs do coordenador, não
    os dos colegas.
- Consequências: o GitHub **não obriga** a aprovação do Renan — o
  `CODEOWNERS` continua `* @guilhermepama` e a aprovação dele não conta
  como de code owner; a regra vale por combinado e pelo histórico dos PRs
  (o marcador deixa as exceções fáceis de achar). Tornar o Renan code
  owner a imporia, mas a aprovação dele passaria a bastar também nos PRs
  dos alunos, contrariando a ADR-005. Mais um passo nos PRs do
  coordenador perto do evento; o prazo menor de 18/10 a 29/10 e a
  exceção cobrem a urgência. Em aberto: um check no `convencoes-pr` que
  exija a aprovação ou o marcador.
