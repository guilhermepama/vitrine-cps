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
  CSV com nome, email, telefone e data/hora do consentimento.
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
- Quando um usuário não autenticado acessa qualquer rota do app, o
  sistema redireciona para o login do admin (guardrail 15).
- Quando um usuário autenticado **sem** a permissão da rota acessa (ex:
  usuário do grupo `digitacao-banca`, spec 06), o sistema responde 403.
- Quando a edição não existe, o sistema responde 404.

### Ranking
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
     alfabética pelo título) — ver perguntas.
- Turma com 1 projeto: `p = b = 1`, final = 1, posição 1.
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
- "Tokens que votaram" = tokens distintos com ao menos 1 voto na edição.
- Visitantes: só a contagem total (os dados ficam no export).

### Relatório operacional
- Lista as estações da edição com total de tokens emitidos, primeira e
  última emissão, e uma grade estação × faixa de 15 min com a contagem.
- Estação sem emissão aparece com 0.
- Não mostra IDs de token, IP nem dado de visitante.

### Export de visitantes
- Só com a permissão específica de export (separada da de ver resultados).
- Colunas: `nome`, `email`, `telefone`, `consentimento_em`. Nenhuma
  coluna de id, token, estação ou voto (guardrail 6).
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
- cadastro: `Edicao` (pesos da nota composta — campo da spec 01),
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
| GET | `/resultados/<edicao_id>/` | `ver_resultados` | HTML: participação + ranking por turma (ou aviso) | 302 login, 403, 404 |
| GET | `/resultados/<edicao_id>/operacional/` | `ver_resultados` | HTML: emissões por estação e por faixa de 15 min | 302 login, 403, 404 |
| GET | `/resultados/<edicao_id>/visitantes.csv` | `exportar_visitantes` | CSV (anexo) | 302 login, 403, 404 |

- `<edicao_id>` validado como inteiro pela rota (guardrail 12); outros
  parâmetros de query são ignorados.
- Só GET; nenhuma rota altera estado. POST/PUT/DELETE → 405.
- Link para as três telas a partir do admin do Django (página da edição),
  se o coordenador aceitar — senão, acesso pela URL.

## Guardrails aplicáveis
6, 11, 12, 13, 15, 16, 17.

- 6: o export e o relatório nunca juntam visitante com token/voto.
- 11: visitantes só em rota com autenticação de admin; nunca em log.
- 12: `edicao_id` validado; nenhuma outra entrada é usada.
- 13: só ORM (`annotate`, `Count`, `Avg`); nenhum SQL cru.
- 15: todas as rotas exigem admin autenticado com permissão.
- 16: migration das permissões versionada.
- 17: testes do cálculo e das permissões entregues junto.

## Critérios de aceite
- [ ] Usuário anônimo nas 3 rotas → redirect para o login
- [ ] Usuário logado sem permissão (ex: grupo `digitacao-banca`) nas 3 rotas → 403
- [ ] Usuário com `ver_resultados` mas sem `exportar_visitantes` → 403 no CSV
- [ ] Edição inexistente → 404; POST em qualquer rota → 405
- [ ] Votação não encerrada → ranking mostra só o aviso, sem nenhum número de voto por projeto
- [ ] Teste do cálculo: turma com votos {10, 5, 0} → `p` = {1; 0,5; 0}
- [ ] Teste do cálculo: todos com o mesmo número de votos → `p = 1` para todos; idem para `b`
- [ ] Teste do cálculo: turma com 1 projeto → final = 1, posição 1
- [ ] Teste do cálculo: com pesos 0,7/0,3, projeto com `b = 1, p = 0` (0,70) fica acima de `b = 0, p = 1` (0,30)
- [ ] Teste do desempate: mesma nota final → maior banca bruta vence; mesma banca → mais votos vence; tudo igual → mesma posição e marca "empate"
- [ ] Projeto sem voto aparece com 0 votos (não some do ranking)
- [ ] Votos de outra edição não entram na contagem
- [ ] Banca pendente → aviso "não é o resultado oficial" e nenhuma nota final exibida
- [ ] Pesos ausentes ou que não somam 1 → erro "Pesos da edição não configurados"
- [ ] CSV tem exatamente as colunas `nome;email;telefone;consentimento_em`, ordenado por nome
- [ ] CSV: nome `=HYPERLINK(...)` sai como `'=HYPERLINK(...)`
- [ ] Nenhum teste/log captura conteúdo do CSV (revisão: só a linha de auditoria com contagem)
- [ ] Relatório operacional soma por estação igual ao total de tokens emitidos na edição
- [ ] Nenhuma tela mostra ID de token ou IP (revisão de template)
- [ ] App não tem migration que crie tabela (revisão: só o model de permissões, `managed = False`)
- [ ] Ranking de uma edição com 5 turmas e ~100 projetos carrega com número de queries fixo (não cresce por projeto — `assertNumQueries`)
- [ ] Testes do caminho crítico passando (cálculo, permissões, export)

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
12. Export: `consentimento_em` com data e hora completas (prova do aceite,
    guardrail 10) ou só a data? Hora exata, junto com `tokens.criado_em`,
    facilita estimar qual token é de qual visitante; quem recebe o CSV é a
    coordenação, fora do sistema. Sugestão: só a data no CSV; a hora fica
    no banco.
