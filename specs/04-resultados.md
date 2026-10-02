# Spec — Resultados e relatórios

- **Responsável**: Renan (@ReCroffi)
- **Status**: rascunho — revisão do coordenador aplicada (PR #14); falta
  só o formato dos dados da banca, que sai na spec 06
- **Depende de**: ADR-002 (stack), ADR-003 (visitantes desacoplados),
  ADR-006 (backup), ADR-007 (nota composta), ADR-008 (banca em ficha),
  spec 01 (edições, turmas, projetos, pesos e `banca_conferida_em`),
  spec 03 (tokens, votos, estações, visitantes), spec 06 (função
  `nota_banca_por_projeto` e formato das notas da banca)

## Objetivo
Dar ao administrador, ao encerrar a votação, o ranking de cada turma pela
**nota composta da ADR-007** (70% banca + 30% público, min-max dentro da
turma), com as duas partes visíveis, totais e participação; mais o
relatório operacional de emissões por estação e o export da lista de
visitantes — tudo em rotas só de admin.

## Escopo
- App `resultados/`, **somente leitura** sobre os dados dos outros apps
  (cadastro, votacao, banca). Não grava voto, nota, projeto nem visitante.
- **Ranking por turma** (`/resultados/<edicao_id>/`): para cada turma da
  edição, tabela com posição, projeto, votos do público, nota de banca
  bruta, `p` e `b` normalizados, nota final e indicação de empate.
  Página pensada para impressão (sem dependência de JS).
- **Participação** (no topo do ranking): tokens emitidos, tokens que
  votaram em ao menos 1 projeto, total de votos, média de votos por token
  votante, visitantes cadastrados (contagem). Por turma: total de votos e
  tokens distintos que votaram em algum projeto da turma.
- **Relatório operacional** (`/resultados/<edicao_id>/operacional/`):
  emissões de token por estação — total, primeira e última emissão.
- **Export de visitantes** (`/resultados/<edicao_id>/visitantes.csv`):
  CSV com nome, email, telefone e a **data** do consentimento (o banco
  guarda data e hora — G10).
- **Cálculo** em função pura, testável sem HTTP (ex:
  `resultados/calculo.py`), recebendo votos e nota de banca por projeto e
  devolvendo o ranking. As views só buscam os dados e chamam essa função.
- `resultados/urls.py` com `app_name = "resultados"` e as três rotas.
- Permissões próprias do app (ver "Dados") e testes do caminho crítico.

## Fora de escopo
- Página **pública** de resultado ou divulgação automática: a coordenação
  divulga a partir da página impressa do admin (decisão do coordenador no
  PR #14).
- Lançar, editar ou conferir notas da banca, e validar o preenchimento da
  ficha (spec 06).
- Calcular a nota de banca do projeto a partir das notas cruas: vem
  pronta do app `banca` (ver "Dados").
- Abrir/encerrar votação, editar pesos ou critérios (specs 03/05/06).
- Qualquer dado por token: lista de tokens, votos de um token, "quem votou
  em quem". Só agregados.
- Cruzar visitante com token ou voto, inclusive por horário (guardrail 6,
  ADR-003).
- Grade de emissões por estação × faixa de horário no relatório
  operacional (decisão do coordenador no PR #14).
- Gráficos, PDF gerado no servidor, export do ranking em CSV/planilha,
  relatórios comparativos entre edições ("relatórios elaborados" ficam
  para a próxima edição — `docs/03-estado.md`).
- "Congelar" o resultado em tabela própria (snapshot): o registro oficial
  é a página impressa e assinada + o `pg_dump` após o resultado (ADR-006)
  — decisão do coordenador no PR #14.
- Critério extra de desempate além de banca bruta e votos.
- Bibliotecas novas (pandas etc.): CSV com o módulo `csv` da biblioteca
  padrão; agregações com o ORM do Django.
- Alterar `urls.py` raiz ou `settings.py`: o coordenador adiciona
  `path("resultados/", include("resultados.urls"))` no PR dos models do
  cadastro (decisão do coordenador no PR #14).

## Comportamento esperado

### Acesso
**Admin**, nesta spec, é a mesma condição de acesso ao admin do Django
(ADR-002): usuário autenticado com `is_active` e `is_staff`. Cada rota
exige admin **e** a permissão dela (superusuário tem todas).

URL cujo `<edicao_id>` não é inteiro não casa com nenhuma rota → 404 do
Django (rota inexistente), antes de qualquer checagem. Nas rotas que
casam, as checagens seguem esta ordem; as de 1 a 3 acontecem antes de
qualquer consulta aos dados de negócio:
1. Quando um usuário não autenticado acessa qualquer rota do app, o
   sistema redireciona para o login do admin (guardrail 15).
2. Quando um usuário autenticado **não admin** acessa (sem `is_staff`),
   o sistema responde 403 — **mesmo que ele tenha a permissão da rota**.
3. Quando um admin **sem** a permissão da rota acessa (ex: usuário do
   grupo `digitacao-banca`, spec 06, que é staff), o sistema responde 403.
4. Quando a edição não existe, o sistema responde 404
   (`get_object_or_404`).

### Validação de entrada (guardrail 12)
- A rota captura `<int:edicao_id>` (conversor do Django) e a view busca a
  edição com `get_object_or_404` — decisão do coordenador no PR #14.
  Entrada que não casa com a rota (`abc`, `-1`, `1.5`) é rota
  inexistente → 404. `0` e números sem edição correspondente → 404.
  Nenhuma validação manual do segmento na view.
- Parâmetros de query são ignorados (não alteram a saída nem geram erro).

### Ranking
- Quando a edição não tem `config_votacao`, o ranking mostra só o aviso
  "Votação desta edição não foi configurada"; a participação aparece com
  as contagens zeradas.
- Quando a votação da edição **ainda não foi encerrada**
  (`config_votacao.encerrada_em` vazio ou no futuro), o ranking mostra só
  o aviso "Resultado disponível após o encerramento da votação" — sem
  votos parciais, sem nota. A participação e o relatório operacional
  continuam disponíveis.
- Quando a votação está encerrada, o sistema, para cada turma:
  1. considera os projetos da turma na edição com status `publicado` —
     o mesmo filtro da cédula da spec 03 (decisão do coordenador no
     PR #14); projeto sem voto entra com 0 votos;
  2. calcula `p = (votos - menor) / (maior - menor)` entre os projetos da
     turma; se maior = menor, `p = 1` para todos;
  3. calcula `b` da mesma forma sobre a nota de banca do projeto
     (ADR-007); se maior = menor, `b = 1`;
  4. `final = peso_banca·b + peso_publico·p`, com os pesos lidos de
     `Edicao.peso_banca` e `Edicao.peso_publico` (0,70 e 0,30 nesta
     edição — ADR-007);
  5. ordena por `final` decrescente; desempate por maior nota de banca
     bruta, depois mais votos do público;
  6. se ainda houver empate em tudo, os projetos recebem a **mesma
     posição** e a linha é marcada "empate" (ordem de exibição
     alfabética pelo título) — decisão do coordenador no PR #14. A
     posição seguinte pula os empatados: dois empatados em 1º →
     posições `1, 1, 3`.
- A normalização é **local à turma**: o máximo e o mínimo de uma turma
  não influenciam outra.
- Turma com 1 projeto: `p = 1`. Se a nota da banca dele estiver
  disponível, `b = 1`, final = 1, posição 1. Sem nota de banca, vale a
  regra de banca pendente abaixo.
- Turma sem projetos: não aparece.
- Os cálculos usam `Decimal`; a tela mostra 2 casas decimais. Nenhum
  arredondamento intermediário entra no cálculo.
- **Banca pendente** (decisão do coordenador no PR #14):
  - Quando `Edicao.banca_conferida_em` está vazio, a conferência das
    notas (30/10) não terminou: **todas** as turmas mostram só a parte do
    público (votos e `p`), com o aviso "Nota da banca pendente — este não
    é o resultado oficial", e **nenhuma** nota final.
  - Quando a conferência está registrada mas algum projeto da turma não
    tem nota de banca (ausente no retorno de `nota_banca_por_projeto`),
    **aquela turma** fica com banca pendente — mesmo aviso, só a parte do
    público, sem nota final. As outras turmas saem normalmente. O projeto
    nunca entra com `b = 0` nem é retirado do ranking.
- Quando os pesos da edição não estão configurados ou não somam 1, a
  página mostra erro "Pesos da edição não configurados" e não calcula.

### Participação
- Contagens sempre agregadas; nenhuma linha identifica um token.
- "Tokens que votaram" = tokens distintos com ao menos 1 voto em
  projeto da edição.
- Média de votos por token votante: com zero tokens votantes, mostra
  "—" (sem divisão por zero).
- Visitantes: só a contagem total (os dados ficam no export).
- **Isolamento por edição** (decisão do coordenador no PR #14):
  - votos: via projeto → turma → edição;
  - tokens emitidos: via estação (`Estacao.edicao_id`, spec 03);
  - visitantes: via `Visitante.edicao_id` **direto** (spec 03,
    preenchido a partir da edição em votação) — nunca via token (G6).
- O ensaio (22/10) é **outra edição** ("Ensaio 2026/2"), com turmas,
  projetos e estações próprios; o isolamento acima já impede que ele
  contamine o resultado do evento. Nada de reabrir votação ou apagar
  dados (decisão do coordenador no PR #14).

### Relatório operacional
- Lista as estações da edição (`Estacao.edicao_id`) com total de tokens
  emitidos, primeira e última emissão.
- Estação sem emissão aparece com total 0 e primeira/última emissão "—".
- Não mostra IDs de token, IP nem dado de visitante.

### Export de visitantes
- Só com a permissão específica de export (separada da de ver resultados).
- Colunas: `nome`, `email`, `telefone`, `consentimento_em`. Nenhuma
  coluna de id, token, estação ou voto (guardrail 6). Só os campos
  permitidos pelo guardrail 9.
- `consentimento_em` sai no CSV **só com a data** (`AAAA-MM-DD`), sem
  hora — decisão do coordenador no PR #14. O banco guarda data e hora do
  aceite (G10, spec 03) e este app não altera isso.
- Visitantes da edição: filtro por `Visitante.edicao_id`.
- Ordenado por nome (não pela ordem de cadastro, que se aproxima da ordem
  de emissão dos tokens).
- Valores que começam com `=`, `+`, `-`, `@`, tab ou CR recebem `'` na
  frente (evita fórmula executada ao abrir no Excel — o nome é digitado
  pelo visitante).
- Codificação UTF-8 com BOM (acentos corretos no Excel), separador `;`.
- O conteúdo do CSV nunca vai para log (guardrail 11); o log registra só
  "export de visitantes por <usuário> em <data/hora>, N linhas".
- Edição sem visitantes: CSV só com o cabeçalho.

## Dados
**Lê** (nomes conforme specs 01, 03 e 06 — o app não altera esses models):
- cadastro: `Edicao` (`peso_banca`, `peso_publico` —
  `DecimalField(max_digits=3, decimal_places=2)`, padrão 0,70 / 0,30;
  `banca_conferida_em`, vazio = banca pendente — spec 01),
  `Turma`, `Projeto` (título, turma, status).
- votacao: `tokens` (id, estacao_id, criado_em), `votos` (token_id,
  projeto_id), `estacoes` (id, nome, edicao_id), `visitantes` (nome,
  email, telefone, consentimento_em, edicao_id), `config_votacao`
  (aberta_em, encerrada_em).
- banca: só pela função `nota_banca_por_projeto(edicao) ->
  {projeto_id: Decimal}`, exposta pelo app `banca` — a regra da nota de
  banca (ADR-007) fica num lugar só (decisão do coordenador no PR #14).
  O `resultados` não lê as notas cruas. Formato interno das notas:
  **pendente da spec 06** (ver "Dependências pendentes").

**Escreve**: nada nos dados de negócio.

**Schema próprio**: um model sem tabela (`managed = False`,
`default_permissions = ()`) só para declarar as permissões
`resultados.ver_resultados` e `resultados.exportar_visitantes`. Migration
versionada no repositório (guardrail 16) — cria apenas o registro das
permissões, nenhuma tabela.

## Endpoints / telas
| Método | Rota | Permissão | Saída | Erros |
|---|---|---|---|---|
| GET | `/resultados/<int:edicao_id>/` | admin + `ver_resultados` | HTML: participação + ranking por turma (ou aviso) | 302 login, 403, 404 |
| GET | `/resultados/<int:edicao_id>/operacional/` | admin + `ver_resultados` | HTML: emissões por estação | 302 login, 403, 404 |
| GET | `/resultados/<int:edicao_id>/visitantes.csv` | admin + `exportar_visitantes` | CSV (anexo) | 302 login, 403, 404 |

- Rotas declaradas em `resultados/urls.py` (`app_name = "resultados"`);
  o prefixo `resultados/` vem do `include` no `urls.py` raiz, adicionado
  pelo coordenador.
- `<int:edicao_id>` na rota + `get_object_or_404` (guardrail 12):
  segmento não inteiro → rota inexistente (404); edição inexistente → 404.
- Só GET; nenhuma rota altera estado. POST/PUT/DELETE → 405.
- Link para as três telas a partir do admin do Django (página da edição),
  se o coordenador aceitar — senão, acesso pela URL.

## Guardrails aplicáveis
6, 9, 10, 11, 12, 13, 15, 16, 17.

- 6: o export e o relatório nunca juntam visitante com token/voto; o
  filtro de visitantes por edição usa `Visitante.edicao_id`, nunca o token.
- 9: o export só contém os campos permitidos (nome, email, telefone,
  consentimento) — nenhum outro dado pessoal.
- 10: o registro de data/hora do aceite fica preservado no banco; o CSV
  sai só com a data, nunca altera o registro.
- 11: visitantes só em rota com autenticação de admin; nunca em log.
- 12: `edicao_id` só entra pelo conversor `<int:>` da rota; não casa →
  404 (rota inexistente); edição inexistente → 404.
- 13: só ORM (`annotate`, `Count`, `Min`, `Max`); nenhum SQL cru.
- 15: todas as rotas exigem admin autenticado com permissão.
- 16: migration das permissões versionada.
- 17: testes do cálculo e das permissões entregues junto.

## Critérios de aceite

**Acesso e validação**
- [ ] Usuário anônimo nas 3 rotas → redirect para o login
- [ ] Usuário autenticado **não admin** (sem `is_staff`) **com** `ver_resultados` e `exportar_visitantes` → 403 nas 3 rotas, inclusive no CSV
- [ ] Admin sem permissão (ex: grupo `digitacao-banca`) nas 3 rotas → 403
- [ ] Admin com `ver_resultados` mas sem `exportar_visitantes` → 403 no CSV
- [ ] `edicao_id` não inteiro (`abc`, `-1`, `1.5`) → 404 nas 3 rotas
- [ ] `edicao_id` inteiro sem edição (`0`, id inexistente) → 404; POST em qualquer rota → 405

**Ranking e cálculo**
- [ ] Edição sem `config_votacao` → aviso "Votação desta edição não foi configurada", participação zerada
- [ ] Votação não encerrada → ranking mostra só o aviso, sem nenhum número de voto por projeto
- [ ] Só projetos com status `publicado` entram no ranking (projeto em outro status da mesma turma não aparece)
- [ ] Teste do cálculo: turma com votos {10, 5, 0} → `p` = {1; 0,5; 0}
- [ ] Teste do cálculo: banca bruta {8,0; 7,0; 6,0} → `b` = {1; 0,5; 0}
- [ ] Teste do cálculo: todos com o mesmo número de votos → `p = 1` para todos; idem para `b`
- [ ] Teste do cálculo: turma com 1 projeto e nota de banca → final = 1, posição 1; sem nota de banca → turma com banca pendente
- [ ] Teste do cálculo: duas turmas com escalas diferentes (turma A votos {100, 50, 0}; turma B votos {4, 2, 0}) → `p` = {1; 0,5; 0} nas duas (normalização local)
- [ ] Teste do cálculo: com pesos 0,70/0,30, projeto com `b = 1, p = 0` (0,70) fica acima de `b = 0, p = 1` (0,30)
- [ ] Teste do desempate: mesma nota final → maior banca bruta vence; mesma banca → mais votos vence; tudo igual → mesma posição e marca "empate"
- [ ] Teste de posição após empate: dois empatados em 1º e um terceiro projeto → posições `1, 1, 3`
- [ ] Projeto sem voto aparece com 0 votos (não some do ranking)
- [ ] `banca_conferida_em` vazio → todas as turmas com aviso "não é o resultado oficial" e nenhuma nota final exibida
- [ ] `banca_conferida_em` preenchido e um projeto da turma A sem nota de banca → turma A com aviso e sem nota final; turma B com ranking oficial
- [ ] Pesos ausentes ou que não somam 1 → erro "Pesos da edição não configurados"

**Participação e operacional**
- [ ] Zero tokens votantes → média de votos por token mostra "—", sem erro
- [ ] Estação sem emissão → total 0 e primeira/última emissão "—"
- [ ] Relatório operacional: soma dos totais por estação igual ao total de tokens emitidos da edição
- [ ] Nenhuma tela mostra ID de token ou IP (revisão de template)

**Isolamento por edição** (fixture com a edição do evento e uma edição "Ensaio")
- [ ] Votos de outra edição não entram no ranking nem na participação
- [ ] Tokens de estações de outra edição não entram na participação nem no relatório operacional
- [ ] Estações de outra edição não aparecem no relatório operacional
- [ ] Visitantes com `edicao_id` de outra edição não entram na contagem nem no CSV
- [ ] O filtro de visitantes não usa token nem estação (revisão de código: só `Visitante.edicao_id`)

**Export de visitantes**
- [ ] CSV tem exatamente as colunas `nome;email;telefone;consentimento_em`, ordenado por nome
- [ ] `consentimento_em` no CSV sai só com a data (`AAAA-MM-DD`, sem hora); o valor no banco continua com data e hora
- [ ] CSV: nome `=HYPERLINK(...)` sai como `'=HYPERLINK(...)`
- [ ] Testes inspecionam o conteúdo do CSV usando só dados fictícios
- [ ] Nenhum log contém dado pessoal: teste com `assertLogs` no export verifica que nome e email fictícios não aparecem; o log tem só usuário, data/hora e número de linhas

**Estrutura**
- [ ] App não tem migration que crie tabela (revisão: só o model de permissões, `managed = False`)
- [ ] `resultados/urls.py` declara `app_name = "resultados"`; o PR não altera `urls.py` raiz nem `settings.py`
- [ ] Ranking com fixture de 5 turmas × 20 projetos (100 projetos, todos com votos) executa o mesmo número de queries que a fixture de 1 turma × 2 projetos (`assertNumQueries`)
- [ ] Testes do caminho crítico passando (cálculo, permissões, validação, export)

## Decisões da revisão (PR #14)
As 13 perguntas em aberto foram respondidas pelo coordenador na revisão
do PR #14; as decisões já estão incorporadas nas seções acima.

**Banca (spec 06):**
1. Formato dos dados da banca (models, campos, jurados, critérios): sai
   na spec 06 (coordenador, até 06/10) e continua como dependência —
   decisão do coordenador no PR #14.
2. A nota de banca do projeto vem pronta da função
   `nota_banca_por_projeto(edicao) -> {projeto_id: Decimal}`, exposta
   pelo app `banca`; a regra fica num lugar só — decisão do coordenador
   no PR #14.
3. Jurado com critérios em branco não acontece: a digitação no admin
   exige todos os critérios da ficha (validação do formulário na
   spec 06) — decisão do coordenador no PR #14.
4. Projeto sem nenhuma avaliação **bloqueia o resultado oficial da
   turma**, que mostra "banca pendente"; `b = 0` puniria o grupo por
   falha da organização — decisão do coordenador no PR #14.
5. A conclusão da conferência é o campo `Edicao.banca_conferida_em`
   (spec 01), preenchido pelo coordenador após a conferência de 30/10;
   vazio = banca pendente — decisão do coordenador no PR #14.

**Outras:**
6. Pesos em `Edicao` (spec 01): `peso_banca` e `peso_publico`,
   `DecimalField(max_digits=3, decimal_places=2)`, padrão 0,70 / 0,30 —
   decisão do coordenador no PR #14.
7. Entram no ranking só projetos `publicado`, o mesmo filtro da cédula da
   spec 03 — decisão do coordenador no PR #14.
8. O ensaio (22/10) é outra edição ("Ensaio 2026/2"), com turmas,
   projetos e estações próprios; nada de reabrir votação ou apagar
   dados — decisão do coordenador no PR #14.
9. Empate total (mesma final, banca e votos): mesma posição; critério
   extra, se a coordenação quiser, entra depois — decisão do coordenador
   no PR #14.
10. Divulgação pública do resultado fica fora de escopo: a coordenação
    divulga a partir da página impressa — decisão do coordenador no
    PR #14.
11. Sem snapshot nesta edição: a página impressa e assinada + o
    `pg_dump` após o resultado (ADR-006) são o registro oficial —
    decisão do coordenador no PR #14.
12. `consentimento_em` no CSV sai só com a data — decisão do coordenador
    no PR #14.
13. Isolamento por edição: `Estacao` ganha `edicao_id` (spec 03) e os
    tokens chegam à edição pela estação; `Visitante` ganha `edicao_id`
    direto, preenchido a partir da edição em votação e nunca do token
    (G6) — decisão do coordenador no PR #14.

## Dependências pendentes
- **Spec 06**: formato dos dados da banca e assinatura final de
  `nota_banca_por_projeto`. A spec 04 fica em `rascunho` até a spec 06
  sair.
- **Specs 01 e 03** precisam trazer os campos usados acima
  (`Edicao.peso_banca`, `Edicao.peso_publico`, `Edicao.banca_conferida_em`,
  `Estacao.edicao_id`, `Visitante.edicao_id`).
