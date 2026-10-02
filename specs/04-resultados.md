# Spec — Resultados e relatórios

- **Responsável**: Renan (@ReCroffi)
- **Status**: rascunho — seções completas; a parte da banca depende da
  spec 06 e das perguntas em aberto abaixo
- **Depende de**: ADR-002 (stack), ADR-003 (visitantes desacoplados),
  ADR-007 (nota composta), ADR-008 (banca em ficha), spec 01 (edições,
  turmas, projetos), spec 03 (tokens, votos, estações, visitantes),
  spec 06 (notas da banca)

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
  emissões de token por estação (total, primeira e última emissão) e por
  estação em faixas de 15 min, para localizar anomalia.
- **Export de visitantes** (`/resultados/<edicao_id>/visitantes.csv`):
  CSV com nome, email, telefone e o momento do consentimento (precisão
  no CSV conforme a pergunta 12; o banco guarda data e hora — G10).
- **Cálculo** em função pura, testável sem HTTP (ex:
  `resultados/calculo.py`), recebendo votos e nota de banca por projeto e
  devolvendo o ranking. As views só buscam os dados e chamam essa função.
- Permissões próprias do app (ver "Dados") e testes do caminho crítico.

## Fora de escopo
- Página **pública** de resultado ou divulgação automática (ver perguntas).
- Lançar, editar ou conferir notas da banca (spec 06).
- Abrir/encerrar votação, editar pesos ou critérios (specs 03/05/06).
- Qualquer dado por token: lista de tokens, votos de um token, "quem votou
  em quem". Só agregados.
- Cruzar visitante com token ou voto, inclusive por horário (guardrail 6,
  ADR-003).
- Gráficos, PDF gerado no servidor, export do ranking em CSV/planilha,
  relatórios comparativos entre edições ("relatórios elaborados" ficam
  para a próxima edição — `docs/03-estado.md`).
- "Congelar" o resultado em tabela própria (snapshot) — ver perguntas.
- Bibliotecas novas (pandas etc.): CSV com o módulo `csv` da biblioteca
  padrão; agregações com o ORM do Django.
- Alterar `urls.py` raiz ou `settings.py`: o `include` das rotas do app é
  pedido ao coordenador.

## Comportamento esperado

### Acesso
**Admin**, nesta spec, é a mesma condição de acesso ao admin do Django
(ADR-002): usuário autenticado com `is_active` e `is_staff`. Cada rota
exige admin **e** a permissão dela (superusuário tem todas). As checagens
seguem esta ordem; as de 1 a 4 acontecem antes de qualquer consulta aos
dados de negócio:
1. Quando um usuário não autenticado acessa qualquer rota do app, o
   sistema redireciona para o login do admin (guardrail 15).
2. Quando um usuário autenticado **não admin** acessa (sem `is_staff`),
   o sistema responde 403 — **mesmo que ele tenha a permissão da rota**.
3. Quando um admin **sem** a permissão da rota acessa (ex: usuário do
   grupo `digitacao-banca`, spec 06, que é staff), o sistema responde 403.
4. Quando `edicao_id` é inválido (ver "Validação de entrada"), o sistema
   responde 400 com a mensagem genérica "Requisição inválida".
5. Quando `edicao_id` é válido mas a edição não existe, o sistema
   responde 404.

### Validação de entrada (guardrail 12)
- A rota captura o segmento `<edicao_id>` como texto, e a view valida
  antes de tocar no banco: só dígitos, de 1 a 9 caracteres, valor maior
  que zero. Qualquer outra coisa (`abc`, `-1`, `0`, `1.5`, 10+ dígitos)
  → 400 "Requisição inválida", sem dizer qual regra falhou.
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
  1. considera os projetos da turma na edição (filtro de status: ver
     perguntas); projeto sem voto entra com 0 votos;
  2. calcula `p = (votos - menor) / (maior - menor)` entre os projetos da
     turma; se maior = menor, `p = 1` para todos;
  3. calcula `b` da mesma forma sobre a nota de banca do projeto
     (ADR-007); se maior = menor, `b = 1`;
  4. `final = peso_banca·b + peso_publico·p`, com os pesos lidos da
     edição (0,7 e 0,3 nesta edição — ADR-007);
  5. ordena por `final` decrescente; desempate por maior nota de banca
     bruta, depois mais votos do público;
  6. se ainda houver empate em tudo, os projetos recebem a **mesma
     posição** e a linha é marcada "empate" (ordem de exibição
     alfabética pelo título) — ver perguntas. A posição seguinte pula
     os empatados: dois empatados em 1º → posições `1, 1, 3`.
- A normalização é **local à turma**: o máximo e o mínimo de uma turma
  não influenciam outra.
- Turma com 1 projeto: `p = 1`. Se a nota da banca dele estiver
  disponível, `b = 1`, final = 1, posição 1. Sem nota de banca, vale a
  regra de banca pendente abaixo (e a pergunta 4).
- Turma sem projetos: não aparece.
- Os cálculos usam `Decimal`; a tela mostra 2 casas decimais. Nenhum
  arredondamento intermediário entra no cálculo.
- Quando as notas da banca ainda não estão disponíveis para a edição
  (nenhuma nota, ou conferência pendente — ver perguntas), o ranking
  mostra só a parte do público (votos e `p`), com o aviso "Nota da banca
  pendente — este não é o resultado oficial", e **não** exibe nota final.
- Quando os pesos da edição não estão configurados ou não somam 1, a
  página mostra erro "Pesos da edição não configurados" e não calcula.

### Participação
- Contagens sempre agregadas; nenhuma linha identifica um token.
- "Tokens que votaram" = tokens distintos com ao menos 1 voto em
  projeto da edição.
- Média de votos por token votante: com zero tokens votantes, mostra
  "—" (sem divisão por zero).
- Visitantes: só a contagem total (os dados ficam no export).
- **Isolamento por edição**: votos são filtrados pela edição via
  projeto → turma → edição. Tokens emitidos e visitantes **não têm
  hoje vínculo com a edição** nos campos da spec 03 — o filtro depende
  da pergunta 13. Para visitantes, o vínculo nunca pode vir do token (G6).

### Relatório operacional
- Lista as estações com total de tokens emitidos, primeira e última
  emissão, e uma grade estação × faixa de 15 min com a contagem. Quais
  estações e tokens pertencem à edição depende da pergunta 13.
- Estação sem emissão aparece com total 0 e primeira/última emissão "—".
- Não mostra IDs de token, IP nem dado de visitante.

### Export de visitantes
- Só com a permissão específica de export (separada da de ver resultados).
- Colunas: `nome`, `email`, `telefone`, `consentimento_em`. Nenhuma
  coluna de id, token, estação ou voto (guardrail 6). Só os campos
  permitidos pelo guardrail 9.
- `consentimento_em`: o banco guarda data e hora do aceite (G10, spec 03)
  e este app não altera isso. A precisão **no CSV** (data e hora, ou só a
  data) segue a resposta à pergunta 12.
- Quais visitantes pertencem à edição depende da pergunta 13.
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
- cadastro: `Edicao` (pesos da nota composta — campo a definir na
  spec 01),
  `Turma`, `Projeto` (título, turma, status).
- votacao: `tokens` (id, estacao_id, criado_em), `votos` (token_id,
  projeto_id), `estacoes` (id, nome), `visitantes` (nome, email, telefone,
  consentimento_em), `config_votacao` (aberta_em, encerrada_em).
- banca: notas por (jurado, projeto, critério) — **formato pendente da
  spec 06** (ver perguntas).

**Escreve**: nada nos dados de negócio.

**Schema próprio**: um model sem tabela (`managed = False`,
`default_permissions = ()`) só para declarar as permissões
`resultados.ver_resultados` e `resultados.exportar_visitantes`. Migration
versionada no repositório (guardrail 16) — cria apenas o registro das
permissões, nenhuma tabela.

## Endpoints / telas
| Método | Rota | Permissão | Saída | Erros |
|---|---|---|---|---|
| GET | `/resultados/<edicao_id>/` | admin + `ver_resultados` | HTML: participação + ranking por turma (ou aviso) | 302 login, 403, 400, 404 |
| GET | `/resultados/<edicao_id>/operacional/` | admin + `ver_resultados` | HTML: emissões por estação e por faixa de 15 min | 302 login, 403, 400, 404 |
| GET | `/resultados/<edicao_id>/visitantes.csv` | admin + `exportar_visitantes` | CSV (anexo) | 302 login, 403, 400, 404 |

- `<edicao_id>` validado pela view conforme "Validação de entrada"
  (guardrail 12): inválido → 400, válido e inexistente → 404.
- Só GET; nenhuma rota altera estado. POST/PUT/DELETE → 405.
- Link para as três telas a partir do admin do Django (página da edição),
  se o coordenador aceitar — senão, acesso pela URL.

## Guardrails aplicáveis
6, 9, 10, 11, 12, 13, 15, 16, 17.

- 6: o export e o relatório nunca juntam visitante com token/voto.
- 9: o export só contém os campos permitidos (nome, email, telefone,
  consentimento) — nenhum outro dado pessoal.
- 10: o registro de data/hora do aceite fica preservado no banco; o
  export pode ter precisão menor (pergunta 12), nunca altera o registro.
- 11: visitantes só em rota com autenticação de admin; nunca em log.
- 12: `edicao_id` validado antes do banco; inválido → 400 genérico.
- 13: só ORM (`annotate`, `Count`, `Avg`); nenhum SQL cru.
- 15: todas as rotas exigem admin autenticado com permissão.
- 16: migration das permissões versionada.
- 17: testes do cálculo e das permissões entregues junto.

## Critérios de aceite

**Acesso e validação**
- [ ] Usuário anônimo nas 3 rotas → redirect para o login
- [ ] Usuário autenticado **não admin** (sem `is_staff`) **com** `ver_resultados` e `exportar_visitantes` → 403 nas 3 rotas, inclusive no CSV
- [ ] Admin sem permissão (ex: grupo `digitacao-banca`) nas 3 rotas → 403
- [ ] Admin com `ver_resultados` mas sem `exportar_visitantes` → 403 no CSV
- [ ] `edicao_id` inválido (`abc`, `-1`, `0`, `1.5`, 10 dígitos) → 400 "Requisição inválida" nas 3 rotas, sem nenhuma query aos dados de negócio (`assertNumQueries` após a autenticação)
- [ ] `edicao_id` válido e inexistente → 404; POST em qualquer rota → 405

**Ranking e cálculo**
- [ ] Edição sem `config_votacao` → aviso "Votação desta edição não foi configurada", participação zerada
- [ ] Votação não encerrada → ranking mostra só o aviso, sem nenhum número de voto por projeto
- [ ] Teste do cálculo: turma com votos {10, 5, 0} → `p` = {1; 0,5; 0}
- [ ] Teste do cálculo: banca bruta {8,0; 7,0; 6,0} → `b` = {1; 0,5; 0}
- [ ] Teste do cálculo: todos com o mesmo número de votos → `p = 1` para todos; idem para `b`
- [ ] Teste do cálculo: turma com 1 projeto e nota de banca → final = 1, posição 1; sem nota de banca → regra de banca pendente
- [ ] Teste do cálculo: duas turmas com escalas diferentes (turma A votos {100, 50, 0}; turma B votos {4, 2, 0}) → `p` = {1; 0,5; 0} nas duas (normalização local)
- [ ] Teste do cálculo: com pesos 0,7/0,3, projeto com `b = 1, p = 0` (0,70) fica acima de `b = 0, p = 1` (0,30)
- [ ] Teste do desempate: mesma nota final → maior banca bruta vence; mesma banca → mais votos vence; tudo igual → mesma posição e marca "empate"
- [ ] Teste de posição após empate: dois empatados em 1º e um terceiro projeto → posições `1, 1, 3`
- [ ] Projeto sem voto aparece com 0 votos (não some do ranking)
- [ ] Banca pendente → aviso "não é o resultado oficial" e nenhuma nota final exibida
- [ ] Pesos ausentes ou que não somam 1 → erro "Pesos da edição não configurados"

**Participação e operacional**
- [ ] Zero tokens votantes → média de votos por token mostra "—", sem erro
- [ ] Estação sem emissão → total 0 e primeira/última emissão "—"
- [ ] Relatório operacional: soma por estação igual ao total de tokens emitidos considerados no relatório (recorte por edição: pergunta 13)
- [ ] Nenhuma tela mostra ID de token ou IP (revisão de template)

**Isolamento por edição** (os três últimos dependem da resposta à pergunta 13)
- [ ] Votos de outra edição não entram no ranking nem na participação
- [ ] Tokens de outra edição não entram na participação nem no relatório operacional
- [ ] Estações/emissões de outra edição não aparecem no relatório operacional
- [ ] Visitantes de outra edição não entram na contagem nem no CSV

**Export de visitantes**
- [ ] CSV tem exatamente as colunas `nome;email;telefone;consentimento_em`, ordenado por nome
- [ ] `consentimento_em` no CSV sai na precisão definida pela pergunta 12; o valor no banco continua com data e hora
- [ ] CSV: nome `=HYPERLINK(...)` sai como `'=HYPERLINK(...)`
- [ ] Testes inspecionam o conteúdo do CSV usando só dados fictícios
- [ ] Nenhum log contém dado pessoal: teste com `assertLogs` no export verifica que nome e email fictícios não aparecem; o log tem só usuário, data/hora e número de linhas

**Estrutura**
- [ ] App não tem migration que crie tabela (revisão: só o model de permissões, `managed = False`)
- [ ] Ranking com fixture de 5 turmas × 20 projetos (100 projetos, todos com votos) executa o mesmo número de queries que a fixture de 1 turma × 2 projetos (`assertNumQueries`)
- [ ] Testes do caminho crítico passando (cálculo, permissões, validação, export)

## Perguntas em aberto
Para o coordenador, **antes de implementar**:

**Dependem da spec 06 (banca) — não resolver por suposição:**
1. Formato dos dados da banca: nomes de models/campos das notas, jurados
   e critérios. A spec 04 só sabe que há uma nota 0–10 por
   (jurado, projeto, critério).
2. Quem calcula a "nota de banca do projeto" da ADR-007 (média dos
   critérios sobre a média dos jurados): o app `banca` expõe uma função
   pronta, ou o `resultados` calcula a partir das notas cruas?
   Sugestão: o `banca` expõe, para a regra ficar num lugar só.
3. Jurado que não deu nota em todos os critérios de um projeto: a média
   usa só os critérios preenchidos, ou a avaliação daquele jurado é
   descartada para aquele projeto?
4. Projeto sem nenhuma avaliação da banca: fica fora do ranking oficial,
   entra com `b = 0`, ou bloqueia o resultado da turma?
5. Como o `resultados` sabe que a **conferência** das notas (30/10) foi
   concluída e o resultado pode ser tratado como oficial? Existe um
   campo/estado na spec 06 (ex: por edição)?

**Outras:**
6. Onde ficam os pesos 70/30 — campo na `Edicao` da spec 01? Nome do campo?
7. Quais projetos entram no ranking: só `publicado`? Deve bater com o
   filtro da cédula da spec 03 (projetos que podiam receber voto).
8. **Dados do ensaio (22/10)**: os votos e tokens de teste ficam em outra
   edição, são apagados antes do evento, ou o resultado deve contar só
   votos dentro de `aberta_em`–`encerrada_em`? Hoje `config_votacao` tem
   uma linha por edição; se for reaberta para o evento, o ensaio pode
   contaminar o resultado.
9. Empate total (mesma final, banca e votos): mesma posição, como
   proposto, ou há critério extra da coordenação?
10. O resultado oficial é divulgado por página pública do sistema ou só
    pela coordenação, a partir da página impressa do admin? (Hoje: fora
    de escopo.)
11. Depois de oficial, o resultado precisa ser congelado (snapshot) para
    não mudar se alguém editar uma nota? Hoje é recalculado a cada acesso.
12. Export: `consentimento_em` **no CSV** com data e hora completas ou
    só a data? O banco guarda data e hora de qualquer forma (G10, spec 03).
    A hora exata não cria por si o vínculo proibido pelo G6, mas, junto
    com `tokens.criado_em`, facilita estimar qual token é de qual
    visitante — e quem recebe o CSV é a coordenação, fora do sistema.
    Sugestão: só a data no CSV.
13. **Isolamento por edição de tokens, estações e visitantes.** Nos campos
    da spec 03, só `config_votacao` e os votos (via projeto → turma) chegam
    à `Edicao`; `tokens`, `estacoes` e `visitantes` não têm vínculo com a
    edição. Como a participação, o relatório operacional e o CSV devem
    filtrar por edição? O vínculo do visitante não pode passar pelo token
    (G6). Precisa ser combinado com os responsáveis das specs 01 e 03;
    os critérios de aceite de isolamento de tokens, estações e visitantes
    dependem desta resposta.
