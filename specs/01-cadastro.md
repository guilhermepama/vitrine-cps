# Spec — Cadastro (edições, cursos, turmas, projetos) e admin

- **Responsável**: Guilherme (@guilhermepama)
- **Status**: implementada — models (PR #17), importação (PR #19) e admin/moderação (3/3)
- **Depende de**: ADR-002 (stack), ADR-006 (R2), ADR-007 (pesos), ADR-009
  (cadastro pelo grupo), spec 00 (esqueleto)
- **Absorve a spec 05**: o admin do cadastro está aqui; estações e
  abrir/encerrar votação ficam na spec 03 (models do app `votacao`).

## Objetivo
Modelo de dados base do sistema e a administração do cadastro: edições,
cursos, turmas e projetos, a importação da lista das coordenações e a
moderação dos projetos antes de irem para a vitrine. É a base que as specs
02, 03, 04 e 06 usam.

## Escopo
- App `cadastro/`: models `Edicao`, `Curso`, `Turma`, `Projeto`,
  `Integrante`, `ImagemProjeto`, com migrations.
- Funções de segurança usadas pela spec 02 (`cadastro/seguranca.py`):
  HMAC do RA, geração e hash do token de edição.
- Validação de upload de imagem (G14) e storage no R2 (ADR-006), com disco
  local quando o R2 não está configurado.
- Comando `importar_lista`: importa o CSV exportado da planilha modelo
  (`docs/modelos/lista-projetos-vitrine-cps.xlsx`).
- Admin: cadastro de edições, cursos e turmas; moderação de projetos
  (publicar e devolver para ajustes em lote), regerar e revogar link de
  edição.
- Mudanças do coordenador fora do app, no mesmo PR: `settings.py`
  (`RA_HMAC_SECRET`, storage do R2), `urls.py` raiz (`include` de
  `resultados/`), `.env.example`.

## Fora de escopo
- Telas do grupo: reivindicar com RA, editar pelo link, rate limit da
  reivindicação (spec 02).
- Página pública `/projeto/<slug>` (spec 02).
- Estações, tokens, votos, visitantes, abrir/encerrar votação (spec 03).
- Jurados, critérios e notas da banca (spec 06). Ranking (spec 04).
- Login de aluno, envio de link por e-mail, painel próprio.
- Redimensionar ou converter imagens (a regravação sem metadados, em
  "Imagens", mantém tamanho e formato); leitura direta de `.xlsx` (só CSV).
- Grupos e permissões de admin além do superusuário (o grupo
  `digitacao-banca` é da spec 06).
- Identidade visual e templates públicos.

## Comportamento esperado

### Edição
- Só **uma edição ativa** por vez (constraint no banco). Ativar outra
  exige desativar a atual antes.
- O ensaio geral (22/10) é uma **edição própria** ("Ensaio 2026/2"), com
  turmas, projetos e estações próprios. Nada do ensaio entra na edição do
  evento.
- **Pesos** (ADR-007): cada um entre 0 e 1 e `peso_banca + peso_publico
  = 1,00` (constraints no banco — `1,70 / −0,70` é recusado). Padrão
  0,70 / 0,30. `peso_banca > peso_publico` é **validação** (`clean()`),
  não constraint: a regra é da ADR-007 desta edição, e uma edição futura
  pode mudá-la por ADR sem migration.
- **Abertura da votação fica na própria edição**: `votacao_aberta_em` e
  `votacao_encerrada_em`. A spec 03 só preenche esses campos (a tabela
  `config_votacao` deixa de existir). Encerramento exige abertura e não
  pode ser anterior a ela (constraint). Depois de preenchido,
  `votacao_aberta_em` **não muda nem é apagado**.
- **Travas depois de abrir a votação** (revisão do Renan no PR #16): a
  partir de `votacao_aberta_em`, ficam fixos — **no model, não só no
  admin** — os pesos da edição e o status e a turma de todos os projetos
  dela (ver "Projeto"). Sem snapshot (PR #14), qualquer mudança aí
  alteraria o resultado em silêncio.
- `prazo_edicao`: depois dele, o link de edição do grupo só mostra o
  conteúdo (a tela é da spec 02; a regra é `Edicao.edicao_aberta()`).
- `banca_conferida_em`: escrito **só** pela conferência da spec 06
  (concluir, reabrir digitação e correção de nota que desfaz), sempre com
  `save(update_fields=["banca_conferida_em"])` e a `Edicao` travada. Fora
  disso o campo é somente leitura: `editable=False` (nenhum formulário do
  admin o recebe) e o `Edicao.save()` **preserva o valor do banco** quando
  `update_fields` não o inclui (save completo de instância carregada antes
  não regrava conferência antiga nem apaga uma nova); edição nova nasce
  vazia. Vazio = resultado da banca pendente (spec 04).

### Curso e turma
- Curso é estável entre edições: sigla única (`DSM`, `GTUR`), nome,
  unidade (`fatec` | `etec`).
- Turma pertence a uma edição e a um curso: `numero_periodo` (1–12) +
  `tipo_periodo` (`semestre` | `ano` | `modulo`) + `turno` opcional.
  Rótulo gerado com a **sigla** do curso: "DSM — 3º semestre", "ADM — 2º ano (tarde)".
- Não pode haver duas turmas iguais na mesma edição (constraint).
- Turma é a **categoria** da cédula (spec 03) e do resultado (spec 04).
- Turma ou curso com projeto não pode ser apagado (`PROTECT`).
- Turma com projeto **não muda de edição nem de curso** (validação no
  model) — os projetos e os votos iriam junto para outra categoria.

### Projeto
- **Slug** gerado uma única vez, na criação, a partir do título
  (`slugify`, sem acento, até 60 caracteres); se já existir, acrescenta
  `-2`, `-3`... O slug **nunca muda**, nem se o título mudar — o link
  público não pode quebrar. Não é editável no admin.
- **Status**:

  | De | Para | Quem / quando |
  |---|---|---|
  | — | `pre_cadastrado` | importação da lista ou admin |
  | `pre_cadastrado`, `ajustes` | `em_revisao` | grupo salva pelo link (spec 02) |
  | `em_revisao` | `publicado` | admin, ação "Publicar" |
  | `em_revisao`, `publicado` | `ajustes` | admin, ação "Devolver para ajustes" |

  Projeto `publicado` **não é editável pelo grupo**. Para corrigir algo
  publicado, o admin devolve para ajustes (a página sai do ar até nova
  aprovação) ou edita ele mesmo no admin.
- **Pré-cadastro** nasce só com turma, título e representante (RA);
  resumo, descrição, capa, links e integrantes podem ficar vazios até o
  grupo preencher. Os requisitos de publicação valem só na ação Publicar.
- **Estado de origem das ações**: Publicar só a partir de `em_revisao`;
  Devolver para ajustes só a partir de `em_revisao` ou `publicado`. Projeto
  em outro estado fica como está e aparece na mensagem da ação em lote.
- **Publicar** exige: capa, resumo, descrição e ao menos 1 integrante.
  Projetos selecionados que não cumprem ficam como estão, e o admin vê
  uma mensagem com quantos foram publicados e quais ficaram de fora e por
  quê.
- **Devolver para ajustes** exige `motivo_ajustes` preenchido (o admin
  escreve no projeto antes de rodar a ação); sem motivo, o projeto fica
  como está e aparece na mensagem.
- `publicado_em` é gravado na primeira publicação e não muda depois.
- `status` é **somente leitura no admin**: muda só pelas ações (Publicar,
  Devolver para ajustes) e pelo fluxo do grupo (spec 02), que aplicam os
  requisitos e as travas.
- **Mudar de turma**: só para outra turma da **mesma edição**, e só antes
  de abrir a votação.
- **Depois de abrir a votação da edição**, o status e a turma do projeto
  não mudam — publicar, devolver para ajustes ou trocar de turma é
  recusado com `ValidationError`. **Não há retirada de projeto no sistema**
  nesta edição: uma desclassificação excepcional é anotada pela
  coordenação no resultado impresso e assinado.
- **Slug**: além de não aparecer no formulário, o `save()` recusa slug
  diferente do gravado (`ValidationError`) — `editable=False` sozinho só
  esconde do formulário (revisão do Renan no #17).

### Regra para quem usa estes models (specs 02, 03, 04 e 06)
As travas vivem no `save()`/`clean()` dos models. `QuerySet.update()` e
`bulk_update()` **passam por cima delas**. Por isso, nos campos travados —
`Edicao`: pesos, `votacao_aberta_em`, `votacao_encerrada_em`; `Turma`:
`edicao`, `curso`; `Projeto`: `slug`, `status`, `turma` — escrita **só por
`save()` na instância ou pelos métodos do model** (`publicar()`,
`devolver_para_ajustes()`), nunca por `update()`. O `/revisar-pr` confere
isso. Uma trava no próprio banco (trigger) seria mais forte, mas é
desproporcional para esta edição (revisão do Renan no #17).

### Equipe (integrantes)
- Lista estruturada: nome de exibição e papel opcional ("Front-end",
  "Pesquisa"), em ordem. Mínimo 1 para publicar, máximo 10.
- O nome é **o que aparece na página pública**. Regra provisória
  (ADR-009, até a coordenação da Etec decidir): projeto de curso da
  **Etec** aceita só o primeiro nome (uma palavra); Fatec aceita nome
  completo. Validação no `clean()` do model, para valer no admin e no
  formulário da spec 02. **A spec 02 precisa acompanhar** (hoje diz
  "primeiro nome" para todos).
- **Fotos de pessoas na Etec** (regra provisória, ADR-009): conferência
  **humana** na moderação — não há detecção automática. Antes de publicar
  projeto da Etec, o admin confere capa e galeria; com foto de pessoa,
  devolve para ajustes com o motivo padrão "Retire as fotos em que
  aparecem pessoas (regra da Etec para menores de idade)".

### Imagens (G14)
- Uma **capa** (obrigatória para publicar; é a imagem da prévia no
  WhatsApp) e até **6 imagens extras**, com legenda opcional (texto
  alternativo).
- Aceita JPG, PNG e WebP, até **3 MB** cada. A validação abre o arquivo
  com Pillow (`verify()`) e confere o formato real — não confia na
  extensão nem no `content_type` enviado.
- Nome do arquivo gerado pelo servidor: `projetos/<uuid4>.<ext>`, com a
  extensão do formato detectado. O nome original nunca é usado.
- Resolução até **25 megapixels** (lida do cabeçalho, sem decodificar):
  acima disso, recusa com mensagem genérica. A limpeza abaixo decodifica a
  imagem inteira na memória.
- **Sem metadados** (decisão do coordenador no parecer do PR #46): ao
  gravar uma imagem nova (`Projeto.save()` e `ImagemProjeto.save()`), o
  servidor a regrava sem EXIF (GPS, data, aparelho), comentário do JPEG
  nem textos do PNG; só a orientação fica. O bucket é público, e a foto de celular traz o
  GPS de onde foi tirada — muitas vezes a casa do aluno, menor de idade
  na Etec. Mesmo tamanho e formato: JPEG com as mesmas tabelas de
  quantização, MPO vira JPEG (primeira imagem), WebP em qualidade 90.
  Efeitos aceitos: imagem animada (APNG, WebP) fica só com o 1º quadro;
  WebP sem perdas passa a ter perdas; JPEG progressivo vira sequencial. O
  arquivo regravado não é conferido de novo contra os 3 MB (nos testes o
  tamanho cai ou fica igual).
- A validação **decodifica** a imagem inteira: foto cortada (upload
  interrompido) é recusada com a mesma mensagem do formato, em vez de
  passar no `verify()` e quebrar na gravação. Custo: até ~100 MB de
  memória por upload no teto de 25 MP.
- Com `R2_BUCKET` definido, as imagens vão para o R2 com URL pública
  pelo `R2_PUBLIC_DOMAIN` (sem URL assinada — ADR-006). Sem ele, disco
  local (desenvolvimento).

### RA e link de edição (ADR-009)
- `hash_ra(ra)`: normaliza e devolve HMAC-SHA256 em hex com
  `RA_HMAC_SECRET`. Normalização: remove espaço, ponto, hífen e barra;
  o que sobra precisa ser **só dígitos, de 5 a 20** (zeros à esquerda
  mantidos). Qualquer outro caractere (letra, por exemplo) → `ValueError`
  — não é descartado em silêncio. Se um formato real de RA tiver letra,
  a importação acusa e a regra é revista.
- `RA_HMAC_SECRET` é variável de ambiente obrigatória, **separada** do
  `QR_HMAC_SECRET`. Sem ela, a aplicação não sobe.
- O RA em claro **nunca** é gravado, logado nem exibido — nem no admin,
  nem no relatório da importação, nem em mensagem de erro (G3, G11).
- `gerar_token_edicao()`: `secrets.token_urlsafe(32)`; devolve o token
  em claro (para mostrar uma vez) e o SHA-256 em hex (para gravar). Token
  em claro nunca é gravado.
- Comparações de hash com `hmac.compare_digest`.
- **Regerar link** (ação do admin, um projeto por vez): grava novo hash;
  o link anterior deixa de valer na hora; o admin vê o link novo **uma
  vez**, na mensagem de confirmação, para repassar ao grupo.
- **Revogar link**: apaga o hash; nenhum link vale até regerar.
- **Projeto criado à mão no admin** (plano B, turma sem lista): o
  formulário tem um campo "RA do representante" **só de escrita** — vazio
  ao abrir, nunca reexibido; ao salvar, grava só o `ra_hmac`. Obrigatório
  na criação; na edição, vazio mantém o atual. Vale a mesma regra de RA
  único por edição.

### Importação da lista
- `python manage.py importar_lista <edicao_id> <arquivo.csv>`:
  **simula** por padrão e só grava com `--aplicar`.
- CSV exportado da aba "Projetos" da planilha, UTF-8 (com ou sem BOM),
  separador `;` ou `,` (detectado). Colunas, pelo cabeçalho: Curso, Turma,
  Período da turma, Nome do projeto, Nome do representante, RA do
  representante.
- Linha de exemplo (projeto começando com "EXEMPLO") e linhas vazias são
  ignoradas.
- Curso: casa pela sigla antes do " — " ("DSM — Desenvolvimento..." →
  `DSM`). Turma: número extraído de "3º semestre" / "2º ano" + período
  (Semestre/Ano/Módulo). A turma **precisa existir** na edição — o admin
  cria as turmas antes; o comando não cria turma.
- **Turno**: coluna "Turno" opcional (a planilha desta edição foi sem
  ela). Com turno, casa exatamente. Sem turno, casa com a única turma
  daquele curso e período; se houver mais de uma (ex: manhã e tarde), a
  linha é erro "turma ambígua — informe o turno" (revisão do Renan no
  PR #16).
- **RA único por edição**: um RA representa no máximo um projeto na
  edição. RA que já representa outro projeto da edição (de importação
  anterior ou de outra linha do arquivo) → erro de linha, sem mostrar o
  RA (revisão do Renan no PR #16).
- Erros por linha: curso inexistente, turma inexistente, turma ambígua,
  período escrito em "Turma" diferente de "Período da turma" (ex: "2º
  ano" com Semestre), título vazio ou com mais de 120 caracteres,
  representante vazio ou com mais de 120 caracteres, RA inválido (regra
  de `hash_ra`), RA de outro projeto da edição, projeto repetido no
  arquivo.
- **Erros de arquivo** (o comando para antes de ler linhas, com mensagem
  e código de saída ≠ 0): edição inexistente; arquivo ausente ou
  ilegível; arquivo que não é UTF-8; cabeçalho sem alguma das colunas
  obrigatórias ou com coluna repetida.
- **Tudo ou nada**: se houver qualquer erro, nada é gravado (transação
  atômica), mesmo com `--aplicar`.
- **Idempotente**: chave = (turma, título normalizado). Título
  normalizado = espaços das pontas removidos, espaços internos repetidos
  viram um, sem acento, em minúsculas (`"  Agenda  Escolar "` ≡
  `"agenda escolar"` ≡ `"Agênda Escolar"`). A comparação com os projetos
  existentes da turma usa a mesma normalização. Projeto que já
  existe e ainda não foi reivindicado tem representante e RA atualizados;
  já reivindicado → linha "ignorada (já reivindicado)", nada muda.
- Relatório na saída: uma linha por linha do CSV com número da linha,
  resultado (criado / atualizado / ignorado / erro) e motivo — **sem o
  RA**. No fim, totais.

## Dados

### `Edicao`
| Campo | Tipo | Regra |
|---|---|---|
| nome | char 60, único | "2026/2", "Ensaio 2026/2" |
| data_evento | date | |
| ativa | bool | **unique quando `ativa = true`** (constraint parcial) |
| prazo_edicao | datetime | |
| peso_banca | decimal(3,2) | padrão 0,70 |
| peso_publico | decimal(3,2) | padrão 0,30; **check: cada peso ≥ 0 e `peso_banca + peso_publico = 1`** (logo, cada um ≤ 1) |
| votacao_aberta_em | datetime, null | preenchido pela spec 03; depois disso, não muda |
| votacao_encerrada_em | datetime, null | **check: só com `votacao_aberta_em` e ≥ ela** |
| banca_conferida_em | datetime, null, `editable=False` | escrito só pela conferência da spec 06, com `update_fields`; o `save()` preserva o valor do banco nos demais saves; nasce vazio. Corrigir nota depois disso **apaga** a conferência (spec 06) |
| criado_em | datetime auto | |

Métodos: `Edicao.objects.ativa()` (a edição ativa ou `None`),
`edicao_aberta()` (agora ≤ `prazo_edicao`), `votacao_foi_aberta()`
(`votacao_aberta_em` preenchido e ≤ agora).

### `Curso`
sigla (char 10, único), nome (char 120), unidade (`fatec` | `etec`), ativo (bool).

### `Turma`
edicao (FK, `PROTECT`), curso (FK, `PROTECT`), numero_periodo (smallint
1–12, check), tipo_periodo (`semestre` | `ano` | `modulo`), turno
(`manha` | `tarde` | `noite` | `integral`, vazio permitido).
**unique (edicao, curso, numero_periodo, tipo_periodo, turno)**.
Propriedade `rotulo`.

### `Projeto`
| Campo | Tipo | Regra |
|---|---|---|
| turma | FK `PROTECT` | |
| titulo | char 120 | |
| slug | slug 70, **único** | gerado na criação, não editável |
| resumo | char 280 | vira a descrição do Open Graph |
| descricao | text, até 3.000 caracteres | |
| componente_origem | char 120, opcional | "PI II — Eventos", "Lab. Web" |
| capa | imagem, null | validação G14 |
| link_repositorio, link_demo, link_video | URL, opcional | só `https://` |
| status | `pre_cadastrado` \| `em_revisao` \| `publicado` \| `ajustes` | índice |
| motivo_ajustes | text, opcional | mostrado ao grupo (spec 02) |
| representante_nome | char 120 | |
| ra_hmac | char 64 | hex; nunca exibido |
| reivindicado_em | datetime, null | |
| token_edicao_hash | char 64, null | **unique quando não nulo** |
| token_edicao_gerado_em | datetime, null | |
| publicado_em | datetime, null | |
| criado_em, atualizado_em | datetime auto | |

### `Integrante`
projeto (FK `CASCADE`), nome (char 60), papel (char 60, opcional), ordem
(smallint). Máximo 10 por projeto (validação do formset).

### `ImagemProjeto`
projeto (FK `CASCADE`), arquivo (imagem, validação G14), legenda (char
120, opcional), ordem (smallint). Máximo 6 por projeto (validação do
formset). A capa fica em `Projeto.capa`, não aqui.

### Variáveis de ambiente novas
`RA_HMAC_SECRET` (obrigatória). As do R2 já estão no `.env.example`.

## Endpoints / telas
Nenhuma rota pública. Tudo no admin do Django (`/admin/`, só superusuário
nesta edição):

| Tela | O que tem |
|---|---|
| Edições | lista com ativa e data do evento; pesos somente leitura após abrir a votação; `votacao_aberta_em`/`votacao_encerrada_em` somente leitura (quem preenche é a spec 03) |
| Cursos | sigla, nome, unidade |
| Turmas | filtro por edição e curso; rótulo |
| Projetos | colunas: título, turma, status, reivindicado (sim/não), atualizado em. Filtros: status, edição, curso. Busca: título, representante. Inlines: integrantes, imagens. Campos `status`, `slug`, `publicado_em`, `reivindicado_em` só leitura; `ra_hmac` e `token_edicao_hash` **fora** do formulário. Ações: Publicar, Devolver para ajustes, Regerar link de edição, Revogar link de edição |

## Guardrails aplicáveis
3, 11, 12, 13, 14, 15, 16, 17.

- 3: `RA_HMAC_SECRET` só em variável de ambiente (por analogia ao segredo do QR).
- 11: RA nunca em log, admin ou relatório da importação.
- 12: validação de tamanhos, URLs, imagens e de cada linha do CSV.
- 13: só ORM.
- 14: tipo real, tamanho e nome gerado pelo servidor nas imagens.
- 15: tudo no admin, com login.
- 16: migrations versionadas.
- 17: testes abaixo.

## Critérios de aceite

**Modelo**
- [ ] Ativar uma segunda edição com outra já ativa → erro de integridade no banco
- [ ] Pesos que não somam 1 → erro de integridade no banco; `1,70 / −0,70` (soma 1, fora de 0–1) → erro de integridade
- [ ] `peso_banca ≤ peso_publico` → `ValidationError` no `full_clean()`
- [ ] Pesos editáveis antes de abrir a votação; depois de abrir (ou de encerrar), salvar pesos novos → `ValidationError` e o banco mantém os anteriores
- [ ] `votacao_encerrada_em` sem `votacao_aberta_em`, ou antes dela → erro de integridade
- [ ] `votacao_aberta_em` preenchido não pode ser alterado nem apagado → `ValidationError`
- [ ] Turma com projeto: mudar edição ou curso → `ValidationError`
- [ ] Duas turmas iguais na mesma edição → erro de integridade
- [ ] Apagar turma ou curso com projeto → bloqueado (`ProtectedError`)
- [ ] Slug gerado na criação; títulos iguais geram `titulo`, `titulo-2`; mudar o título não muda o slug
- [ ] Integrante de projeto Etec com nome de duas palavras → `ValidationError`; Fatec aceita
- [ ] Rótulo da turma: `DSM — 3º semestre`, `ADM — 2º ano (tarde)`
- [ ] `edicao_aberta()`: antes do prazo → verdadeiro; exatamente no prazo → verdadeiro; depois → falso
- [ ] Edição nasce com `banca_conferida_em` vazio

**Segurança**
- [ ] `hash_ra("123.456 789")` = `hash_ra("123-456/789")` = `hash_ra("123456789")`; zeros à esquerda preservados
- [ ] RA com letra, com menos de 5 ou mais de 20 dígitos, ou vazio → `ValueError`
- [ ] Sem `RA_HMAC_SECRET`, a aplicação não sobe
- [ ] Token de edição: hash gravado ≠ token; regerar invalida o hash anterior; revogar deixa nulo
- [ ] Nenhuma tela do admin mostra `ra_hmac` nem `token_edicao_hash` (teste do formulário)

**Imagens**
- [ ] Arquivo `.jpg` que não é imagem → recusado
- [ ] PNG renomeado para `.jpg` → aceito e gravado com extensão `.png`
- [ ] Imagem de 3,1 MB → recusada; GIF → recusado
- [ ] Nome gravado = `projetos/<uuid>.<ext>`, sem o nome original
- [ ] Sétima imagem extra → recusada pelo formset
- [ ] JPEG e WebP com EXIF de GPS, aparelho e orientação → gravados sem GPS nem aparelho, com a orientação; PNG perde EXIF e textos (capa e imagem extra)
- [ ] JPEG gravado mantém formato e tamanho em pixels; MPO continua `.jpg`
- [ ] Salvar o projeto de novo não regrava a capa já gravada
- [ ] PNG de poucos KB com mais de 25 megapixels → recusado
- [ ] Comentário do JPEG não chega ao arquivo gravado
- [ ] JPEG cortado → recusado na validação; salvo sem validar → nada gravado

**Moderação**
- [ ] Publicar em lote: projeto completo vira `publicado` com `publicado_em`; projeto sem capa fica em `em_revisao` e aparece na mensagem
- [ ] Devolver sem `motivo_ajustes` → não muda; com motivo → `ajustes`
- [ ] Publicar a partir de `pre_cadastrado` ou `ajustes` → não muda; devolver a partir de `pre_cadastrado` ou `ajustes` → não muda
- [ ] Pendências de publicação: sem resumo, sem descrição e sem integrante são reportados cada um
- [ ] Republicar não altera `publicado_em`
- [ ] Com a votação aberta: publicar, devolver para ajustes e trocar a turma do projeto → `ValidationError`, nada muda no banco
- [ ] Trocar a turma do projeto para turma de outra edição → `ValidationError`, mesmo antes de abrir a votação
- [ ] `status` não é editável no formulário do admin
- [ ] Slug alterado direto no model (`p.slug = "outro"; p.save()`) → `ValidationError`, slug do banco inalterado
- [ ] `votacao_foi_aberta()`: nulo → falso; passado e instante exato → verdadeiro; futuro → falso
- [ ] Publicar enquanto outra transação abre a votação → espera e é recusado (teste de concorrência)
- [ ] Foto de celular no formato MPO → aceita e gravada como `.jpg`
- [ ] Dois projetos da mesma edição com o mesmo RA → `ValidationError` no `full_clean()`, sem o RA na mensagem
- [ ] Projeto criado no admin com RA → grava só `ra_hmac`; o campo de RA volta vazio ao reabrir
- [ ] 11º integrante → recusado pelo formset do admin (o formulário do grupo é testado na spec 02)
- [ ] Usuário anônimo no admin → login (G15)

**Importação**
- [ ] CSV com `;` e com `,`, com e sem BOM → mesmo resultado
- [ ] Sem `--aplicar` → nada gravado e relatório completo
- [ ] Uma linha com erro → nada gravado, mesmo com `--aplicar`; relatório aponta a linha e o motivo
- [ ] Rodar duas vezes o mesmo CSV → nenhum projeto duplicado; reimportar com o título variando em espaços, maiúsculas e acentos → mesmo projeto
- [ ] Arquivo ausente, não UTF-8, sem coluna obrigatória ou com coluna repetida, e edição inexistente → mensagem e saída ≠ 0, nada gravado
- [ ] "2º ano" com período "Semestre" → erro de linha; representante com 121 caracteres → erro de linha
- [ ] Projeto já reivindicado → "ignorado", RA não muda
- [ ] Linha "EXEMPLO" ignorada; turma inexistente → erro
- [ ] Duas turmas que só diferem no turno: linha sem turno → erro "turma ambígua", nada gravado; linha com turno → casa a turma certa
- [ ] RA que já representa outro projeto da edição (importação anterior) → erro de linha; o mesmo RA em outra edição é aceito
- [ ] O RA não aparece na saída do comando em nenhum caso (teste captura a saída)
- [ ] Testes do caminho crítico passando

## Perguntas em aberto
Não bloqueiam a implementação:
- **Etec (coordenação)**: cursos e turmas participantes; se o técnico é
  "módulo" ou "semestre"; regra para menores (hoje: só primeiro nome,
  sem foto de pessoas).
- Prazo de edição desta edição: proposta 20/10, 23h59 (antes do pré-ensaio).
- Spec 03 (Renan): trocar `config_votacao` pelos campos
  `Edicao.votacao_aberta_em` / `votacao_encerrada_em`; spec 04 acompanha
  (onde diz "sem `config_votacao`", vale "`votacao_aberta_em` vazio").
  **Abrir a votação** grava `votacao_aberta_em` dentro de
  `transaction.atomic()` com `select_for_update()` na linha da `Edicao` —
  a mesma trava que `Projeto.save()` usa, para publicar e abrir ao mesmo
  tempo não furar a regra (parecer do #17).
- Planilha modelo: incluir a coluna "Turno" na próxima edição.
- Spec 02 (Cleiton): nome completo para Fatec, só primeiro nome para
  Etec; projeto `publicado` não editável pelo grupo — testado lá.
- Spec 06: corrigir nota depois da conferência apaga
  `banca_conferida_em`; quem digita não confere.
- Divulgação dos pesos antes do evento (ADR-007): é da coordenação
  (comunicação), não do sistema.
