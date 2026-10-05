# Spec — Avaliação da banca

- **Responsável**: Guilherme (@guilhermepama)
- **Status**: pronta para implementar — depois das respostas às
  "Perguntas em aberto"
- **Depende de**: ADR-002 (stack), ADR-007 (nota composta, critérios),
  ADR-008 (banca em ficha impressa), spec 01 (`Edicao`, `Turma`,
  `Projeto`, `banca_conferida_em`), spec 04 (consome
  `nota_banca_por_projeto`)

## Objetivo
Registrar as notas 0–10, por critério, que cada jurado deu aos projetos
da edição — escritas em **ficha impressa e assinada** no evento e
digitadas no admin depois (ADR-008) — e entregar à spec 04 a nota de
banca de cada projeto, já conferida.

## Escopo
- App `banca/`: models `Criterio`, `Jurado`, `Avaliacao` e `Nota`, com
  migrations (G16).
- Admin de critérios e jurados (só superusuário).
- **Digitação** no admin: uma `Avaliacao` por (jurado, projeto), com uma
  `Nota` por critério da edição em inline. Feita pelo grupo
  `digitacao-banca`, criado por data migration com as permissões exatas.
- **Ficha para imprimir**, por jurado e de todos os jurados da edição,
  gerada a partir dos critérios, das turmas do jurado e dos projetos
  publicados.
- **Conferência**: página do coordenador com a amostra a conferir contra
  as fichas e a ação que preenche `Edicao.banca_conferida_em`.
- Função `nota_banca_por_projeto(edicao)` em `banca/servicos.py`, a única
  regra da nota de banca (ADR-007), consumida pela spec 04.

## Fora de escopo
- Login de jurado e tela de avaliação no celular (próxima edição, ADR-008).
- Cálculo da nota final, normalização, ranking e exibição (spec 04).
- Qualquer vínculo com tokens, votos ou visitantes do público.
- Peso diferente por critério: todos os critérios pesam igual (ADR-007).
- Copiar critérios ou jurados de uma edição para outra (são poucos; o
  admin cadastra de novo).
- Página pública com nota ou nome de jurado. Notas por jurado nunca saem
  do admin.
- Importar notas de planilha ou OCR das fichas.
- Conflito de interesse (jurado que orientou o projeto): regra da
  coordenação, não do sistema.

## Comportamento esperado

### Critérios
- Cadastrados por edição no admin (superusuário): nome (até 60), texto de
  apoio para a ficha (até 200, opcional) e ordem.
- Nome e ordem únicos por edição (constraint no banco).
- **Travados depois de aberta a votação** (`Edicao.votacao_aberta_em`
  preenchido): criar, alterar ou apagar critério da edição →
  `ValidationError`, e nada muda. Os critérios são divulgados antes do
  evento (ADR-007), como os pesos.
- Critério com nota não pode ser apagado (`PROTECT`).

### Jurados
- Registro sem login (ADR-008): nome (até 120), edição e **turmas que
  avalia** (uma ou mais, da mesma edição).
- Por que turmas: a normalização é min-max **dentro da turma** (ADR-007).
  Se cada projeto de uma turma tiver jurados diferentes, a nota mede o
  jurado, não o projeto. Distribuindo a banca por turma, todos os
  projetos da turma passam pelos mesmos jurados.
- Nome único por edição. Turma de outra edição → `ValidationError` no
  formulário do admin.
- Jurado pode ser cadastrado depois de aberta a votação (substituto no
  dia). Jurado com avaliação não pode ser apagado (`PROTECT`).

### Ficha impressa
- Página HTML para imprimir em A4, sem JavaScript: cabeçalho com a edição,
  o nome do jurado, a escala "0 a 10, uma casa decimal (ex.: 7,5)", a
  legenda dos critérios (nome e texto de apoio) e as linhas "Assinatura" e
  "Data".
- Tabela por turma do jurado: uma linha por projeto **publicado** da
  turma, ordenada por título, com o **número do projeto** (o `id`) e o
  título; uma coluna em branco por critério, na ordem cadastrada.
- Rota da edição inteira: as fichas de todos os jurados, uma por página
  (`page-break`), para imprimir de uma vez.
- Se a votação da edição ainda não foi aberta, a ficha mostra no topo
  "Lista provisória: projetos podem mudar até a abertura da votação" e a
  data e hora em que foi gerada.
- Ficha sem projeto (jurado sem turma, ou turmas sem publicados) mostra
  "Nenhum projeto publicado nas turmas deste jurado" e não quebra.
- Não mostra RA, representante, integrantes nem link de edição — só número
  e título.

### Digitação (admin, grupo `digitacao-banca`)
- Tela "Avaliações": escolhe o jurado e o projeto e digita uma nota por
  critério da edição, num formulário só. Salvar grava a `Avaliacao` e
  todas as `Nota` numa transação.
- **Todos os critérios são obrigatórios**: o inline tem exatamente um
  campo por critério da edição (sem linhas extras, sem apagar linha).
  Faltou um → erro no formulário, nada gravado (decisão 3 do PR #14 da
  spec 04).
- Nota: decimal com uma casa, de 0,0 a 10,0. Fora disso, mais de uma
  casa ou texto → erro no formulário; e o banco tem check
  `0 ≤ valor ≤ 10`.
- Recusas, com `ValidationError` no formulário e nada gravado:
  - jurado e projeto de edições diferentes;
  - projeto fora das turmas do jurado;
  - projeto que não está `publicado`;
  - edição com a votação ainda não aberta (antes disso a turma e o status
    dos projetos podem mudar — spec 01);
  - (jurado, projeto) já digitado → "Esta ficha já foi digitada; edite a
    existente." (constraint única no banco, além da validação).
- **Linha incompleta na ficha** (jurado deixou critério em branco ou
  rasurado): a digitação **não** inventa nem completa. A linha fica sem
  digitar e vai para o coordenador, que resolve com o jurado. Regra de
  operação (roteiro da Barbara), não do sistema.
- **Linha toda em branco** = jurado não avaliou o projeto: não se digita
  nada (ADR-007: jurado não precisa avaliar todos).
- **Registro de quem digitou**: `digitado_por` e `digitado_em` na
  criação; `alterado_por` e `alterado_em` a cada alteração. Preenchidos
  pelo servidor, somente leitura no admin. O histórico do admin
  (`LogEntry`) guarda cada mudança.
- **Correção depois da conferência**: salvar uma `Avaliacao` ou `Nota` de
  uma edição com `banca_conferida_em` preenchido **apaga**
  `banca_conferida_em`, na mesma transação, com a linha da `Edicao`
  travada (spec 01). O resultado volta a "banca pendente" até nova
  conferência. Mensagem no admin: "A conferência desta edição foi
  desfeita; confira de novo."
- O grupo não apaga avaliações. Apagar (ficha digitada para o jurado ou
  projeto errado) é do superusuário, e também desfaz a conferência.
- Mudanças só por `save()`/`delete()` dos models ou do admin, nunca
  `QuerySet.update()`, que passaria por cima do registro e da regra da
  conferência (regra do coordenador no PR #17).

### Conferência (coordenador)
- Página da edição, só superusuário:
  - contagem de avaliações digitadas, por jurado;
  - projetos publicados **sem nenhuma avaliação**, por turma (a turma
    fica com banca pendente na spec 04 — decisão 4 do PR #14);
  - **amostra a conferir**: 20% das avaliações da edição, no mínimo 10 (ou
    todas, se houver menos), sorteadas com semente fixa por edição — a
    mesma amostra a cada vez que a página abre, até mudar o conjunto de
    avaliações. Cada linha mostra jurado, número e título do projeto e as
    notas, na ordem da ficha.
- Botão **Concluir conferência** (POST com CSRF): preenche
  `banca_conferida_em = agora`, com a `Edicao` travada.
  - **Quem digitou não confere**: se o usuário aparece como
    `digitado_por` em alguma avaliação da edição → recusa com "Quem
    digitou fichas desta edição não pode concluir a conferência." e nada
    muda.
  - Sem nenhuma avaliação na edição → recusa.
  - Já conferida → recusa, nada muda.
- Erro achado na amostra: o coordenador corrige pelo admin. Isso desfaz a
  conferência (acima), e ele conclui de novo depois de conferir.
- Projetos sem avaliação **não** impedem concluir: a spec 04 mostra a
  turma como pendente. A página mostra o aviso antes do botão.

### Nota de banca do projeto (`nota_banca_por_projeto`)
- `nota_banca_por_projeto(edicao) -> dict[int, Decimal]`, em
  `banca/servicos.py`.
- Regra (ADR-007): para cada avaliação, a média das notas dos critérios;
  para o projeto, a média dessas médias entre os jurados que o avaliaram.
- Só projetos `publicado` da edição; projeto sem avaliação **não aparece**
  no dicionário (a spec 04 trata a ausência como banca pendente).
- Resultado em `Decimal` com 4 casas (`ROUND_HALF_EVEN`), sem `float`.
- Uma consulta só ao banco, qualquer que seja o número de projetos.
- Não olha `banca_conferida_em`: quem decide se o resultado é oficial é a
  spec 04.

## Dados

Tabelas novas (migrations do app `banca`):

| Model | Campo | Tipo e regra |
|---|---|---|
| `Criterio` | edicao | FK `cadastro.Edicao`, `PROTECT` |
| | nome | char(60) |
| | apoio | char(200), opcional (texto da ficha) |
| | ordem | smallint ≥ 1 |
| | — | únicos: (edicao, nome), (edicao, ordem) |
| `Jurado` | edicao | FK `Edicao`, `PROTECT` |
| | nome | char(120); único por edição |
| | turmas | M2M `cadastro.Turma` (mesma edição, validado no formulário) |
| `Avaliacao` | jurado | FK `Jurado`, `PROTECT` |
| | projeto | FK `cadastro.Projeto`, `PROTECT` |
| | digitado_por, alterado_por | FK `User`, `PROTECT`; `alterado_por` nulo |
| | digitado_em, alterado_em | datetime; `alterado_em` nulo |
| | — | única: (jurado, projeto) |
| `Nota` | avaliacao | FK `Avaliacao`, `CASCADE` |
| | criterio | FK `Criterio`, `PROTECT` |
| | valor | decimal(3,1); check `0 ≤ valor ≤ 10` |
| | — | única: (avaliacao, criterio) — "uma avaliação por (jurado, projeto, critério)" |

- **Permissões**: data migration cria o grupo `digitacao-banca` com
  `add`/`change`/`view` de `Avaliacao` e `Nota` e `view` de `Jurado` e
  `Criterio`. Sem `delete`, sem nada de `votacao`, sem `Edicao`, sem
  visitantes. Permissões próprias em `Jurado.Meta`: `imprimir_ficha` e
  `concluir_conferencia`, dadas só ao superusuário (que tem todas).
- Lê de `cadastro`: `Edicao` (`votacao_aberta_em`, `banca_conferida_em`),
  `Turma`, `Projeto` (`status`, `titulo`, `turma`). Escreve em `cadastro`
  só `Edicao.banca_conferida_em`, pelo `save()` da instância travada.

## Endpoints / telas

| Rota | Quem | Entrada | Saída | Erros |
|---|---|---|---|---|
| Admin `Criterio`, `Jurado` | superusuário | formulário | CRUD | `ValidationError` (travas e edição) |
| Admin `Avaliacao` (+ inline `Nota`) | superusuário e `digitacao-banca` | jurado, projeto, uma nota por critério | grava tudo ou nada | `ValidationError` (acima) |
| `GET /admin/banca/jurado/<id>/ficha/` | `banca.imprimir_ficha` | `id` inteiro | HTML para imprimir | sem permissão → 403; anônimo → login; inexistente → 404 |
| `GET /admin/banca/edicao/<id>/fichas/` | `banca.imprimir_ficha` | `id` inteiro | todas as fichas | idem |
| `GET /admin/banca/edicao/<id>/conferencia/` | `banca.concluir_conferencia` | `id` inteiro | contagens, sem avaliação, amostra | idem |
| `POST /admin/banca/edicao/<id>/conferencia/` | `banca.concluir_conferencia` | CSRF | preenche `banca_conferida_em`, volta à página com mensagem | recusas acima (sem mudar nada); sem CSRF → 403 |

- As rotas ficam no `admin` do app (`get_urls` do `ModelAdmin`), com
  `admin_view` — sessão de staff e `never_cache` (G15).
- `id` validado como inteiro pelo conversor da rota (G12).

## Guardrails aplicáveis
- **12** — entrada validada: nota decimal 0–10 com uma casa, ids
  inteiros, mesma edição, projeto publicado.
- **13** — só ORM; a média sai de uma consulta parametrizada, sem SQL cru.
- **15** — todas as rotas no admin, com login de staff e permissão
  específica; o grupo de digitação não vê votos, visitantes nem
  configurações.
- **16** — models, constraints e o grupo `digitacao-banca` em migrations.
- **17** — testes do caminho crítico: unicidade, obrigatoriedade dos
  critérios, travas, desfazer a conferência, "quem digita não confere",
  permissões e a regra de `nota_banca_por_projeto`.
- **6 e 10 (por analogia)** — nenhuma ligação com tokens, votos ou
  visitantes; nome de jurado e notas por jurado nunca em página pública.

## Critérios de aceite

**Modelo**
- [ ] Duas notas para o mesmo (avaliação, critério) → erro de integridade no banco
- [ ] Duas avaliações para o mesmo (jurado, projeto) → erro de integridade no banco
- [ ] Nota 10,1 ou −0,1 gravada direto no model → erro de integridade (check)
- [ ] Critério com mesmo nome ou mesma ordem na edição → erro de integridade
- [ ] Apagar critério ou jurado com nota → `ProtectedError`
- [ ] Criar, alterar ou apagar critério depois de aberta a votação → `ValidationError` e o banco sem mudança
- [ ] Jurado com turma de outra edição → erro no formulário do admin

**Digitação**
- [ ] Formulário com todos os critérios preenchidos → 1 `Avaliacao` + N `Nota`, com `digitado_por` = usuário e `digitado_em` preenchido
- [ ] Um critério em branco → erro no formulário, nada gravado
- [ ] Nota `7,55`, `11`, `abc` → erro no formulário, nada gravado
- [ ] Projeto de outra edição, fora das turmas do jurado, ou não publicado → erro, nada gravado
- [ ] Edição com votação não aberta → erro, nada gravado
- [ ] (jurado, projeto) já digitado → erro com a mensagem da spec, nada gravado
- [ ] Alterar uma nota → `alterado_por`/`alterado_em` preenchidos; `digitado_*` não mudam
- [ ] Alterar ou apagar com `banca_conferida_em` preenchido → `banca_conferida_em` vazio na mesma transação
- [ ] `QuerySet.update()` não aparece no app `banca` (teste de revisão de código)

**Permissões**
- [ ] Grupo `digitacao-banca` existe depois do `migrate`, com exatamente as permissões da spec
- [ ] Usuário do grupo: cria e altera avaliação; apagar → 403; abrir admin de votos, visitantes, edições, critérios (alterar) ou jurados (alterar) → 403
- [ ] Usuário do grupo nas rotas de ficha e de conferência → 403; anônimo → login
- [ ] Superusuário acessa tudo

**Ficha**
- [ ] Ficha do jurado lista só projetos publicados das turmas dele, por turma e título, com número e título; uma coluna por critério, na ordem
- [ ] Ficha não contém RA, nome do representante, integrantes nem link de edição (teste de conteúdo)
- [ ] Antes de abrir a votação, a ficha mostra o aviso de lista provisória; depois, não
- [ ] Jurado sem projeto → mensagem da spec, status 200
- [ ] Rota da edição traz uma ficha por jurado, separadas por quebra de página
- [ ] Página sem `<script>`

**Conferência**
- [ ] Amostra: 20% das avaliações, mínimo 10 (ou todas, se menos); a mesma em duas aberturas seguidas
- [ ] Página lista os projetos publicados sem avaliação, por turma
- [ ] Concluir com usuário que digitou alguma avaliação da edição → recusa com a mensagem, `banca_conferida_em` vazio
- [ ] Concluir sem avaliações, ou já conferida → recusa, nada muda
- [ ] Concluir válido → `banca_conferida_em` preenchido
- [ ] POST sem CSRF → 403

**Nota de banca**
- [ ] Jurado A dá {8, 6} e jurado B dá {10, 10} ao projeto → 8,5 (média de 7 e 10), `Decimal("8.5000")`
- [ ] Projeto sem avaliação não aparece no dicionário
- [ ] Projeto não publicado ou de outra edição não aparece
- [ ] Resultado é `Decimal`, nunca `float`
- [ ] Mesmo número de consultas com 2 e com 100 projetos (`assertNumQueries`)
- [ ] Testes do caminho crítico passando

## Plano de fatias (PRs até ~300 linhas)
1. `banca: models, migrations, grupo e nota_banca_por_projeto` — destrava a
   spec 04.
2. `banca: digitação no admin` (inlines, validações, registro, desfazer a
   conferência).
3. `banca: ficha para imprimir`.
4. `banca: conferência`.

A fatia 1 entra antes de 15/10, para a spec 04 ter a função real; as
demais até 20/10 (entrega da banca). O ensaio de 22/10 testa a digitação
de fichas de teste na edição "Ensaio 2026/2".

## Critérios propostos para a edição 2026/2 (conteúdo, não código)
> Proposta do coordenador para a coordenação bater o martelo, extraída dos
> PPCs em `docs/docs-seed/`. Os critérios são cadastrados por edição no
> admin, então esta lista é o conteúdo sugerido para 2026/2, não uma lista
> fixa no código. Escala: 0–10.

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

## Perguntas em aberto
1. **Critérios × ADR-007.** A ADR-007 diz que os critérios "medem
   impacto, não execução técnica — escolha da coordenação" e lista
   impacto social, ambiental e, a confirmar, comercial. A proposta acima
   inclui execução (4) e apresentação (5). Se a coordenação aceitar os 6,
   a mudança fica registrada numa linha nova da ADR-007. Não bloqueia o
   código: critério é dado da edição.
2. **Nota com uma casa decimal** (7,5) ou só inteiros? A spec assume uma
   casa, porque a ADR-007 cita notas como 6,5.
3. **Jurado por turma** (desta spec) ou jurado avaliando quaisquer
   projetos? Por turma deixa a normalização justa; exige que a coordenação
   distribua a banca por turma.
4. **Amostra de 20%, mínimo 10**: o tamanho serve para a conferência de
   30/10?
5. **Pesos e critérios divulgados antes do evento** (ADR-007): quem
   publica e onde (site da Fatec, regulamento)? Fora do sistema, mas com
   prazo antes de 29/10.
