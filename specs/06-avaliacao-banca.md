# Spec — Avaliação da banca

- **Responsável**: Guilherme (@guilhermepama)
- **Status**: pronta para implementar
- **Depende de**: ADR-002 (stack), ADR-007 (nota composta, critérios),
  ADR-008 (banca em ficha impressa), spec 01 (`Edicao`, `Turma`,
  `Projeto`, `banca_conferida_em`), spec 04 (consome
  `nota_banca_por_projeto`)

## Objetivo
Registrar as notas 0–10, por critério, que cada jurado deu aos projetos
das turmas que avaliou — escritas em **ficha impressa e assinada** no
evento e digitadas no admin depois (ADR-008) — e entregar à spec 04 a
nota de banca de cada projeto.

## Escopo
- App `banca/`: models `Criterio`, `Jurado`, `Avaliacao` e `Nota`, com
  migrations (G16).
- Admin de critérios e jurados (só superusuário).
- **Digitação** no admin, em dois passos (jurado, depois projeto e
  notas), pelo grupo `digitacao-banca`.
- **Ficha para imprimir**, por jurado e de todos os jurados da edição.
- **Conferência**: página com cobertura das fichas e a amostra a conferir,
  e a ação que preenche `Edicao.banca_conferida_em`.
- Função `nota_banca_por_projeto(edicao)` em `banca/servicos.py`, a única
  regra da nota de banca (ADR-007), consumida pela spec 04.
- Um ajuste no admin do `cadastro` (código do coordenador):
  `banca_conferida_em` passa a ser somente leitura na tela de `Edicao`.
  Só a ação de conferência e as correções desta spec o escrevem.

## Fora de escopo
- Login de jurado e tela de avaliação no celular (próxima edição, ADR-008).
- Cálculo da nota final, normalização, ranking e exibição (spec 04).
- Qualquer vínculo com tokens, votos ou visitantes do público.
- Peso diferente por critério: todos pesam igual (ADR-007).
- Copiar critérios ou jurados de uma edição para outra (o admin cadastra
  de novo; são poucos).
- Página pública com nota ou nome de jurado. Notas por jurado nunca saem
  do admin e da ficha.
- Importar notas de planilha ou OCR das fichas.
- Registro no sistema de "linha incompleta" da ficha (fica no papel, com
  o coordenador — ver "Digitação").
- Conflito de interesse (jurado que orientou o projeto): regra da
  coordenação, não do sistema.

## Comportamento esperado

### Critérios
- Cadastrados por edição no admin (superusuário): nome (até 60), texto de
  apoio para a ficha (até 200, opcional) e ordem (≥ 1).
- Nome e ordem únicos por edição (constraint no banco).
- **Travados depois de aberta a votação** (`Edicao.votacao_aberta_em`
  preenchido): criar ou alterar critério da edição → `ValidationError` no
  `clean()`, conferido com a linha da `Edicao` travada
  (`select_for_update`), como o `Projeto.save()` da spec 01. Nada muda.
  Os critérios são divulgados antes do evento (ADR-007), como os pesos.
- Apagar: o admin não oferece a exclusão de critério de edição com votação
  aberta (`has_delete_permission` falso para esses objetos, e sem a ação
  em lote `delete_selected` no `CriterioAdmin`). Critério com nota →
  `PROTECT`.

### Jurados
- Registro sem login (ADR-008), só com o **nome** — nada de contato, CPF
  ou e-mail. Edição e **turmas que avalia** (uma ou mais, da mesma
  edição).
- **Jurado por turma** (decisão do coordenador): a normalização é min-max
  dentro da turma (ADR-007). Se projetos da mesma turma tivessem jurados
  diferentes, a nota mediria o jurado, não o projeto. A coordenação
  distribui a banca por turma.
- Nome único por edição. Turma de outra edição → erro no formulário do
  admin.
- **Travas do jurado com avaliação**: não muda de edição e não perde uma
  turma onde já tem avaliação → erro no formulário. Não pode ser apagado
  (`PROTECT`; o admin não oferece a exclusão).
- Jurado pode ser cadastrado depois de aberta a votação (substituto no
  dia).
- No admin, o rótulo do jurado leva a edição ("Ensaio 2026/2 · Maria"),
  porque o ensaio convive com a edição real.

### Ficha impressa
- Página HTML para imprimir em A4, sem JavaScript, com:
  - cabeçalho com a edição, o nome do jurado e a escala "0 a 10, uma casa
    decimal (ex.: 7,5)";
  - legenda dos critérios (nome e texto de apoio), na ordem cadastrada;
  - linhas "Assinatura" e "Data";
  - rodapé com a data e hora em que foi gerada, sempre.
- Tabela por turma do jurado: uma linha por projeto **publicado**, ordenada
  por título, com o **número do projeto** (o `id`, impresso como `#17`,
  igual ao rótulo da digitação) e o título, e uma coluna em branco por
  critério.
- **Identificação em toda página** (decisão do coordenador no parecer do
  PR #56): o cabeçalho de cada tabela (`thead`, que o navegador repete em
  cada página impressa) traz uma linha com edição, jurado e turma. Folha
  solta continua identificável, e o nome da turma não fica órfão no pé
  da página.
- Se a votação da edição ainda não foi aberta, a ficha mostra no topo
  "Lista provisória: projetos podem mudar até a abertura da votação".
- **Operação** (roteiro da Barbara): imprimir as fichas oficiais depois
  que a moderação terminar. No dia 29, depois de abrir a votação,
  conferir na página de conferência se há projeto publicado fora das
  fichas e, se houver, reimprimir a ficha daquele jurado. Projeto fora da
  ficha fica sem avaliação e trava o resultado oficial da turma
  (decisão 4 do PR #14 da spec 04).
- Rota da edição inteira: as fichas de todos os jurados, uma por página
  (`page-break`), para imprimir de uma vez.
- Jurado sem projeto (sem turma, ou turmas sem publicados) mostra "Nenhum
  projeto publicado nas turmas deste jurado", status 200.
- Não mostra RA, representante, integrantes nem link de edição.

### Digitação (admin, grupo `digitacao-banca`)
- **Dois passos.** "Adicionar avaliação" pede primeiro o jurado (lista
  das edições com votação aberta, com o rótulo do jurado). Escolhido, o
  formulário abre com `?jurado=<id>`: jurado fixo, campo de projeto
  limitado aos publicados das turmas dele, com o rótulo
  "#<id> — <título> (<turma>)", e uma nota por critério da edição.
  "Salvar e adicionar outra" volta ao formulário com o mesmo jurado, para
  digitar a ficha inteira em sequência.
- **Só edição aberta e não conferida** (decisão do coordenador no parecer
  do PR #55): o passo 1 e o `?jurado=` do passo 2 aceitam só jurados de
  edições com votação aberta **e** `banca_conferida_em` vazio; os demais
  voltam ao passo 1. Assim o ensaio e as edições passadas não recebem
  ficha por engano. Corrigir uma avaliação existente continua pela
  alteração, que desfaz a conferência.
- **Inline das notas**: `min_num = max_num =` número de critérios da
  edição, `extra = 0`, `validate_min = validate_max = True`,
  `can_delete = False`, critério oculto e fixo em cada linha, valor
  obrigatório (sem `empty_permitted`). O `clean()` do formset exige que o
  conjunto de critérios enviados seja **igual** ao da edição do jurado
  (protege contra POST adulterado).
- Salvar grava a `Avaliacao` e todas as `Nota` numa transação.
- **Nota**: decimal com uma casa, de 0,0 a 10,0, digitada com **vírgula**
  (`localize=True` no campo). `7,5` passa; `7,55`, `11`, `-1` ou texto →
  erro no formulário. O banco tem check `0 ≤ valor ≤ 10`.
- Recusas, com erro no formulário e nada gravado:
  - jurado e projeto de edições diferentes;
  - projeto fora das turmas do jurado;
  - projeto que não está `publicado`;
  - nota de critério de outra edição;
  - edição com a votação ainda não aberta (antes disso, turma e status dos
    projetos podem mudar — spec 01);
  - edição sem nenhum critério cadastrado;
  - (jurado, projeto) já digitado → "Esta ficha já foi digitada; edite a
    existente." (`UniqueConstraint` com `violation_error_message`).
- Erro de formulário no admin volta com status 200 e os erros na tela
  (padrão do admin). É a exceção ao "400" do G12, que vale para os
  endpoints próprios.
- **Linha incompleta na ficha** (critério em branco ou rasurado): não se
  digita a linha. A ficha vai para o coordenador, que resolve com o
  jurado. Regra de operação, não do sistema.
- **Linha toda em branco** = jurado não avaliou o projeto: não se digita
  nada (ADR-007: jurado não precisa avaliar todos). A página de
  conferência mostra a cobertura, para a falta não passar despercebida.
- **Registro de quem digitou**: `digitado_em` (`auto_now_add`) e
  `digitado_por` na criação; `alterado_por` e `alterado_em` a cada
  alteração **com mudança** (`form.has_changed()` do pai ou de algum form
  do inline, em `save_related`). Somente leitura no admin. O histórico do
  admin (`LogEntry`) guarda cada mudança. As contas de digitação são
  **desativadas** depois do evento, nunca apagadas (`PROTECT`).
- **Correção depois da conferência**: qualquer criação, alteração com
  mudança ou exclusão de `Avaliacao` ou `Nota` de uma edição com
  `banca_conferida_em` preenchido **apaga** `banca_conferida_em`, na mesma
  transação, com a linha da `Edicao` travada, via
  `edicao.save(update_fields=["banca_conferida_em"])` (spec 01). Salvar
  sem mudança não mexe em nada.
  - Feito em receptores `post_save`/`post_delete` de `Avaliacao` e `Nota`.
    O `post_delete` é disparado por objeto também nas exclusões em lote do
    admin (`queryset.delete()`) e nas `Nota` apagadas em cascata; o
    `delete()` do model não é usado para isso.
  - Mensagem no admin: "A conferência desta edição foi desfeita; confira
    de novo."
- O grupo não apaga avaliações. Apagar (ficha digitada para o jurado ou o
  projeto errado) é do superusuário.
- Nenhum `QuerySet.update()` nem `bulk_update` no app (regra do
  coordenador no PR #17).

### Conferência
- Página da edição, para quem tem `banca.concluir_conferencia`:
  - **cobertura por jurado**: avaliações digitadas / projetos publicados
    nas turmas dele;
  - **cobertura por turma**: projetos publicados **sem nenhuma
    avaliação** (a turma fica com banca pendente na spec 04 — decisão 4
    do PR #14) e projetos com menos jurados que os da turma;
  - **amostra a conferir**: 20% das avaliações da edição, arredondado para
    cima, no mínimo 10 (ou todas, se houver menos). Sorteio
    determinístico: semente = sha256 de `edicao_id` mais os ids das
    avaliações em ordem, `random.Random(semente).sample(...)`. A mesma
    amostra em qualquer worker e a cada abertura, até mudar o conjunto de
    avaliações. Cada linha mostra jurado, número e título do projeto,
    quem digitou e as notas na ordem da ficha.
- **Achou erro na amostra** → o coordenador confere **todas** as
  avaliações daquele digitador (a página filtra por digitador), corrige
  pelo admin e confere de novo. A correção desfaz a conferência.
- Botão **Concluir conferência** (POST com CSRF): preenche
  `banca_conferida_em = agora`, com a `Edicao` travada. Recusas, sem mudar
  nada, voltando à página (302) com a mensagem:
  - **quem digitou não confere**: usuário que é `digitado_por` em alguma
    avaliação da edição → "Quem digitou fichas desta edição não pode
    concluir a conferência." Correção feita depois (`alterado_por`) não
    impede;
  - votação da edição ainda não encerrada;
  - nenhuma avaliação na edição;
  - já conferida.
- **Quem confere**: a permissão `concluir_conferencia` é dada ao
  coordenador e ao Renan (decisão do coordenador): se o coordenador
  digitar fichas no dia 30, o Renan conclui.
- Projetos sem avaliação **não** impedem concluir: a página mostra o aviso
  antes do botão, e a spec 04 mostra a turma como pendente.

### Nota de banca do projeto (`nota_banca_por_projeto`)
- `nota_banca_por_projeto(edicao) -> dict[int, Decimal]`, em
  `banca/servicos.py`.
- Regra (ADR-007): para cada avaliação, a média das notas dos critérios;
  para o projeto, a média dessas médias entre os jurados que o avaliaram.
- **Uma consulta**: como toda avaliação tem exatamente os N critérios da
  edição (obrigatórios, e travados antes da digitação), a média das
  médias é igual a `Avg("valor")` das notas agrupado por projeto. Um teste
  guarda essa premissa (toda avaliação da edição tem N notas).
- Só projetos `publicado` da edição; projeto sem avaliação **não aparece**
  no dicionário (a spec 04 trata a ausência como banca pendente).
- Resultado em `Decimal`, como sai do `AVG` do Postgres, **sem
  arredondar** (spec 04: nenhum arredondamento intermediário). Nunca
  `float`.
- Não olha `banca_conferida_em`: quem decide se o resultado é oficial é a
  spec 04.

## Dados

Tabelas novas (migrations do app `banca`):

| Model | Campo | Tipo e regra |
|---|---|---|
| `Criterio` | edicao | FK `cadastro.Edicao`, `PROTECT` |
| | nome | char(60) |
| | apoio | char(200), opcional (texto da ficha) |
| | ordem | smallint; check `ordem ≥ 1` |
| | — | únicos: (edicao, nome), (edicao, ordem) |
| `Jurado` | edicao | FK `Edicao`, `PROTECT` |
| | nome | char(120); único por edição |
| | turmas | M2M `cadastro.Turma` (mesma edição, validado no formulário) |
| `Avaliacao` | jurado | FK `Jurado`, `PROTECT` |
| | projeto | FK `cadastro.Projeto`, `PROTECT` |
| | digitado_por | FK `User`, `PROTECT` |
| | digitado_em | datetime, `auto_now_add` |
| | alterado_por | FK `User`, `PROTECT`, nulo |
| | alterado_em | datetime, nulo |
| | — | única: (jurado, projeto), com `violation_error_message` |
| `Nota` | avaliacao | FK `Avaliacao`, `CASCADE` |
| | criterio | FK `Criterio`, `PROTECT` |
| | valor | decimal(3,1); check `0 ≤ valor ≤ 10` |
| | — | única: (avaliacao, criterio) — "uma avaliação por (jurado, projeto, critério)" |

- **Permissões próprias** em `Jurado.Meta.permissions`: `imprimir_ficha`
  ("Pode imprimir a ficha da banca") e `concluir_conferencia` ("Pode
  concluir a conferência da banca"). O superusuário tem as duas; o
  coordenador dá `concluir_conferencia` ao usuário do Renan no admin.
- **Grupo `digitacao-banca`**: criado por um receptor `post_migrate`
  idempotente em `BancaConfig.ready()` (as `Permission` só existem depois
  do `post_migrate`; uma data migration não as encontraria num banco
  novo — CI, testes, primeiro deploy). Permissões: `add`/`change`/`view`
  de `Avaliacao` e `Nota` e `view` de `Jurado` e `Criterio`. Sem
  `delete`, nada de `votacao`, de `Edicao` nem de visitantes. Rodar o
  `migrate` de novo não duplica nem acrescenta permissões.
- Lê de `cadastro`: `Edicao` (`votacao_aberta_em`, `votacao_encerrada_em`,
  `banca_conferida_em`), `Turma`, `Projeto` (`status`, `titulo`, `turma`).
  Escreve em `cadastro` só `Edicao.banca_conferida_em`, pelo `save()` da
  instância travada.
- **Retenção**: nomes de jurados e notas ficam no banco como registro do
  resultado oficial, como os projetos da edição. Não há outro dado pessoal
  de jurado.

## Endpoints / telas

| Rota | Quem | Entrada | Saída | Erros |
|---|---|---|---|---|
| Admin `Criterio`, `Jurado` | superusuário | formulário | CRUD | erro no formulário (travas e edição) |
| Admin `Avaliacao` (+ inline `Nota`) | superusuário e `digitacao-banca` | jurado (`?jurado=<id>`), projeto, uma nota por critério | grava tudo ou nada | erro no formulário (acima); `?jurado` inexistente ou de edição sem votação aberta → volta ao passo 1 |
| `GET /admin/banca/jurado/<int:id>/ficha/` | `banca.imprimir_ficha` | id | HTML para imprimir | staff sem permissão → 403; não staff ou anônimo → login do admin; inexistente → 404 |
| `GET /admin/banca/jurado/edicao/<int:id>/fichas/` | `banca.imprimir_ficha` | id da edição | todas as fichas | idem |
| `GET /admin/banca/jurado/edicao/<int:id>/conferencia/` | `banca.concluir_conferencia` | id da edição; `?digitador=<id>` opcional | cobertura, amostra | idem |
| `POST /admin/banca/jurado/edicao/<int:id>/conferencia/` | `banca.concluir_conferencia` | CSRF | preenche `banca_conferida_em`; 302 para a página com mensagem | recusas → 302 com a mensagem, nada muda; sem CSRF → 403 |

- As rotas próprias saem do `get_urls()` do `JuradoAdmin` e vêm **antes**
  das padrão (senão o `<path:object_id>/` do admin as captura), envolvidas
  em `admin_site.admin_view` (sessão de staff e `never_cache`, G15).
- Ids validados pelo conversor `<int:>` da rota (G12).

## Guardrails aplicáveis
- **12**: entrada validada (nota com uma casa entre 0 e 10, ids inteiros,
  mesma edição, projeto publicado, critérios da edição). Admin devolve 200
  com erros no formulário; as rotas próprias recusam com 302 e mensagem.
- **13**: só ORM; a média sai de uma consulta, sem SQL cru.
- **15**: tudo no admin, com login de staff e permissão específica; o
  grupo de digitação não vê votos, visitantes nem configurações.
- **16**: models, constraints e permissões em migrations; o grupo nasce do
  `post_migrate`, sem passo manual.
- **17**: testes do caminho crítico, listados abaixo.
- **6 e 10 (por analogia)**: nenhuma ligação com tokens, votos ou
  visitantes; nome de jurado e notas por jurado nunca em página pública.

## Critérios de aceite

**Modelo**
- [ ] Duas notas para o mesmo (avaliação, critério) → erro de integridade no banco
- [ ] Duas avaliações para o mesmo (jurado, projeto) → erro de integridade no banco
- [ ] Nota 10,1 ou −0,1 gravada direto no model → erro de integridade (check)
- [ ] Critério com mesmo nome ou mesma ordem na edição, ou ordem 0 → erro de integridade
- [ ] Criar ou alterar critério depois de aberta a votação → `ValidationError` e o banco sem mudança
- [ ] Admin não oferece apagar critério de edição com votação aberta, nem jurado com avaliação (`has_delete_permission` falso; sem `delete_selected`)
- [ ] Jurado com turma de outra edição → erro no formulário
- [ ] Jurado com avaliação: mudar de edição ou tirar turma com avaliação → erro no formulário

**Digitação**
- [ ] Passo 1 lista só jurados de edições com votação aberta; passo 2 lista só projetos publicados das turmas do jurado
- [ ] Formulário com todos os critérios → 1 `Avaliacao` + N `Nota`, `digitado_por` = usuário, `digitado_em` preenchido
- [ ] Um critério em branco → erro, nada gravado
- [ ] POST adulterado com critério a menos, a mais ou de outra edição → erro, nada gravado
- [ ] `7,5` aceito; `7,55`, `11`, `-1`, `abc` → erro, nada gravado
- [ ] Projeto de outra edição, fora das turmas do jurado, ou não publicado → erro, nada gravado
- [ ] Edição com votação não aberta, ou sem critérios → erro, nada gravado
- [ ] (jurado, projeto) já digitado → erro com a mensagem da spec, nada gravado
- [ ] Alterar uma nota → `alterado_por`/`alterado_em` preenchidos; `digitado_*` sem mudança
- [ ] Abrir e salvar sem mudar nada → nenhum campo muda e a conferência continua
- [ ] Com `banca_conferida_em` preenchido: alterar uma nota, criar avaliação, apagar uma avaliação e apagar em lote pelo admin → `banca_conferida_em` vazio em cada caso
- [ ] Nenhum `.update(`, `bulk_update`, `bulk_create` nem `delete()` de QuerySet no app `banca` fora dos testes (teste de revisão de código)

**Permissões**
- [ ] Grupo `digitacao-banca` existe depois do `migrate` num banco novo, com exatamente as permissões da spec; rodar `migrate` de novo não muda o grupo
- [ ] Usuário do grupo: cria e altera avaliação; apagar → 403; alterar critério ou jurado → 403; admin de votos, visitantes ou edições → 403
- [ ] Usuário do grupo nas rotas de ficha e de conferência → 403; anônimo → login do admin
- [ ] Usuário com `concluir_conferencia` (sem ser superusuário) abre e conclui a conferência

**Ficha**
- [ ] Ficha do jurado lista só projetos publicados das turmas dele, por turma e título, com número e título; uma coluna por critério, na ordem; rodapé com a hora de geração
- [ ] Ficha não contém RA, nome do representante, integrantes nem link de edição (teste de conteúdo)
- [ ] Antes de abrir a votação, mostra o aviso de lista provisória; depois, não
- [ ] Jurado sem projeto → mensagem da spec, status 200
- [ ] Rota da edição traz uma ficha por jurado, separadas por quebra de página
- [ ] Página sem `<script>`

**Conferência**
- [ ] Amostra: 20% arredondado para cima, mínimo 10 (ou todas, se menos); a mesma em duas aberturas e em dois processos (semente sha256)
- [ ] `?digitador=<id>` lista todas as avaliações daquele digitador
- [ ] Página mostra cobertura por jurado e os projetos publicados sem avaliação, por turma
- [ ] Concluir com usuário que digitou alguma avaliação da edição → recusa com a mensagem; `banca_conferida_em` vazio
- [ ] Usuário que só corrigiu (`alterado_por`) consegue concluir
- [ ] Concluir com votação não encerrada, sem avaliações, ou já conferida → recusa, nada muda
- [ ] Concluir válido → `banca_conferida_em` preenchido
- [ ] POST sem CSRF → 403
- [ ] `banca_conferida_em` é somente leitura no admin de `Edicao`

**Nota de banca**
- [ ] Jurado A dá {8, 6} e jurado B dá {10, 10} ao projeto → 8,5 (média de 7 e 10)
- [ ] Projeto sem avaliação, não publicado ou de outra edição não aparece no dicionário
- [ ] Resultado é `Decimal`, nunca `float`, sem arredondamento
- [ ] Premissa da consulta única: toda avaliação da edição tem N notas
- [ ] Mesmo número de consultas com 2 e com 100 projetos (`assertNumQueries`)
- [ ] Testes do caminho crítico passando

## Plano de fatias (PRs até ~300 linhas)
1. `banca: models, grupo, desfazer conferência e nota_banca_por_projeto`.
   Inclui os receptores `post_save`/`post_delete` e o `post_migrate` do
   grupo. Destrava a spec 04, que usa a função e a regra da conferência
   nos testes.
2. `banca: admin de critérios e jurados` (travas, rótulos, turmas).
3. `banca: digitação em dois passos` (inline, validações, registro).
4. `banca: ficha para imprimir`.
5. `banca: conferência` (cobertura, amostra, conclusão) e
   `banca_conferida_em` somente leitura no admin de `Edicao`.

A fatia 1 entra antes de 15/10; as demais até 20/10 (entrega da banca). O
ensaio de 22/10 testa a digitação de fichas de teste na edição "Ensaio
2026/2".

## Decisões do coordenador incorporadas
1. **Nota com uma casa decimal**, digitada com vírgula (ADR-007 cita 6,5).
2. **Jurado por turma**: todos os projetos da turma passam pelos mesmos
   jurados; a coordenação distribui a banca por turma.
3. **Quem confere**: coordenador e Renan; quem digitou não confere;
   correção feita depois não impede.
4. **Amostra de 20%, mínimo 10**; achou erro → todas as avaliações daquele
   digitador.

## Critérios propostos para a edição 2026/2 (conteúdo, não código)
> Proposta do coordenador para a coordenação bater o martelo, tirada dos
> PPCs de DSM e GTUR (os PDFs ficam fora do repositório; o resumo dos
> cursos está em `docs/referencias/cursos.md`). Os critérios são
> cadastrados por edição no admin, então esta lista é o conteúdo sugerido
> para 2026/2, não código. Escala: 0–10.

| # | Critério | O que o jurado avalia | Âncora nos PPCs |
|---|---|---|---|
| 1 | Problema e impacto social | O projeto ataca um problema real e relevante? Para quem? | Socioemocional "resolver problemas complexos" (DSM §4.2 = GTUR §4.2); temáticas transversais "atendimento a demandas sociais" (§4.3) |
| 2 | Inovação e criatividade | A solução é nova, ou resolve de um jeito diferente? | "soluções criativas e inovadoras" (§4.2); DSM "projetar soluções inovadoras baseadas em TI" (§4.1) |
| 3 | Sustentabilidade e impacto ambiental | Reduz desperdício, preserva, educa? | Temáticas transversais: "sustentabilidade… preservação e educação ambiental" (§4.3, ambos); GTUR componente "Ecoturismo e Sustentabilidade" |
| 4 | Qualidade da execução | O entregue funciona e está bem construído, no nível do curso? | DSM §2.5: "execução do produto", "atendimento às normas"; DSM qualidade/testes/segurança (§4.1); GTUR viabilidade e planejamento (§4.1) |
| 5 | Apresentação e comunicação | O grupo explica com clareza problema, solução e resultados no estande? | DSM §2.5 (lista literal): "clareza na expressão oral e escrita", "adequação ao público-alvo", "comunicabilidade", "argumentação consistente" |
| 6 | Viabilidade e potencial de aplicação | Vira produto/serviço real? Há quem use ou pague? | DSM "empreender… identificar oportunidades" (§4.1); GTUR "avaliar mercados", "estudo de viabilidade econômica" (§4.1); §2.5 aceita "modelagem/plano de negócios" como evidência |

- Redação neutra de curso: vale para DSM, GTUR e Etec sem adaptação.
- "Trabalho em equipe" (forte nos PPCs) ficou de fora de propósito: o
  jurado no estande não observa o processo interno do grupo. Se a
  coordenação quiser, entra como pergunta da arguição, não como nota.
- 6 critérios é o teto prático para ficha A4 preenchida em pé no estande.

## Perguntas em aberto (não bloqueiam o código)
1. **Critérios × ADR-007.** A ADR-007 diz que os critérios "medem
   impacto, não execução técnica — escolha da coordenação" e lista
   impacto social, ambiental e, a confirmar, comercial. A proposta acima
   inclui execução (4) e apresentação (5). Se a coordenação aceitar os 6,
   a mudança fica registrada numa linha nova da ADR-007. Critério é dado
   da edição: o código não muda.
2. **Divulgação dos pesos e critérios antes do evento** (ADR-007): quem
   publica e onde (site da Fatec, regulamento)? Fora do sistema, com
   prazo antes de 29/10.
