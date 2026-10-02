# Spec — Cadastro (edições, cursos, turmas, projetos) e admin

- **Responsável**: Guilherme (@guilhermepama)
- **Status**: em implementação (PR 1/3: models)
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
- Redimensionar ou converter imagens; leitura direta de `.xlsx` (só CSV).
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
- `peso_banca + peso_publico = 1,00` (constraint no banco). Padrão
  0,70 / 0,30 (ADR-007). Quando a votação da edição já foi aberta (spec 03:
  `config_votacao.aberta_em` preenchido), os pesos ficam **somente
  leitura** no admin.
- `prazo_edicao`: depois dele, o link de edição do grupo só mostra o
  conteúdo (a tela é da spec 02; a regra é `Edicao.edicao_aberta()`).
- `banca_conferida_em`: preenchido pelo coordenador após a conferência das
  fichas (30/10). Vazio = resultado da banca pendente (spec 04).

### Curso e turma
- Curso é estável entre edições: sigla única (`DSM`, `GTUR`), nome,
  unidade (`fatec` | `etec`).
- Turma pertence a uma edição e a um curso: `numero_periodo` (1–12) +
  `tipo_periodo` (`semestre` | `ano` | `modulo`) + `turno` opcional.
  Rótulo gerado: "DSM — 3º semestre", "Administração — 2º ano (tarde)".
- Não pode haver duas turmas iguais na mesma edição (constraint).
- Turma é a **categoria** da cédula (spec 03) e do resultado (spec 04).
- Turma ou curso com projeto não pode ser apagado (`PROTECT`).

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
- **Publicar** exige: capa, resumo, descrição e ao menos 1 integrante.
  Projetos selecionados que não cumprem ficam como estão, e o admin vê
  uma mensagem com quantos foram publicados e quais ficaram de fora e por
  quê.
- **Devolver para ajustes** exige `motivo_ajustes` preenchido (o admin
  escreve no projeto antes de rodar a ação); sem motivo, o projeto fica
  como está e aparece na mensagem.
- `publicado_em` é gravado na primeira publicação e não muda depois.

### Equipe (integrantes)
- Lista estruturada: nome de exibição e papel opcional ("Front-end",
  "Pesquisa"), em ordem. Mínimo 1 para publicar, máximo 10.
- O nome é **o que aparece na página pública**. Regra provisória
  (ADR-009, até a coordenação da Etec decidir): projeto de curso da
  **Etec** aceita só o primeiro nome (uma palavra); Fatec aceita nome
  completo. Validação no `clean()` do model, para valer no admin e no
  formulário da spec 02.

### Imagens (G14)
- Uma **capa** (obrigatória para publicar; é a imagem da prévia no
  WhatsApp) e até **6 imagens extras**, com legenda opcional (texto
  alternativo).
- Aceita JPG, PNG e WebP, até **3 MB** cada. A validação abre o arquivo
  com Pillow (`verify()`) e confere o formato real — não confia na
  extensão nem no `content_type` enviado.
- Nome do arquivo gerado pelo servidor: `projetos/<uuid4>.<ext>`, com a
  extensão do formato detectado. O nome original nunca é usado.
- Com `R2_BUCKET` definido, as imagens vão para o R2 com URL pública
  pelo `R2_PUBLIC_DOMAIN` (sem URL assinada — ADR-006). Sem ele, disco
  local (desenvolvimento).

### RA e link de edição (ADR-009)
- `hash_ra(ra)`: normaliza (só dígitos; espaços e pontuação removidos;
  zeros à esquerda mantidos) e devolve HMAC-SHA256 em hex com
  `RA_HMAC_SECRET`. RA vazio ou sem dígito → `ValueError`.
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
- Erros por linha: curso inexistente, turma inexistente, título vazio ou
  com mais de 120 caracteres, representante vazio, RA sem dígitos, RA
  repetido no arquivo, projeto repetido no arquivo.
- **Tudo ou nada**: se houver qualquer erro, nada é gravado (transação
  atômica), mesmo com `--aplicar`.
- **Idempotente**: chave = (turma, título normalizado). Projeto que já
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
| peso_publico | decimal(3,2) | padrão 0,30; **check `peso_banca + peso_publico = 1`** |
| banca_conferida_em | datetime, null | |
| criado_em | datetime auto | |

Métodos: `Edicao.objects.ativa()` (a edição ativa ou `None`),
`edicao_aberta()` (agora ≤ `prazo_edicao`).

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
| Edições | lista com ativa e data do evento; pesos somente leitura após abrir a votação |
| Cursos | sigla, nome, unidade |
| Turmas | filtro por edição e curso; rótulo |
| Projetos | colunas: título, turma, status, reivindicado (sim/não), atualizado em. Filtros: status, edição, curso. Busca: título, representante. Inlines: integrantes, imagens. Campos `slug`, `publicado_em`, `reivindicado_em` só leitura; `ra_hmac` e `token_edicao_hash` **fora** do formulário. Ações: Publicar, Devolver para ajustes, Regerar link de edição, Revogar link de edição |

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
- [ ] Pesos que não somam 1 → erro de integridade no banco
- [ ] Duas turmas iguais na mesma edição → erro de integridade
- [ ] Apagar turma ou curso com projeto → bloqueado (`ProtectedError`)
- [ ] Slug gerado na criação; títulos iguais geram `titulo`, `titulo-2`; mudar o título não muda o slug
- [ ] Integrante de projeto Etec com nome de duas palavras → `ValidationError`; Fatec aceita
- [ ] Rótulo da turma: `DSM — 3º semestre`, `ADM — 2º ano (tarde)`

**Segurança**
- [ ] `hash_ra("123.456 789")` = `hash_ra("123456789")`; zeros à esquerda preservados; RA sem dígito → `ValueError`
- [ ] Sem `RA_HMAC_SECRET`, a aplicação não sobe
- [ ] Token de edição: hash gravado ≠ token; regerar invalida o hash anterior; revogar deixa nulo
- [ ] Nenhuma tela do admin mostra `ra_hmac` nem `token_edicao_hash` (teste do formulário)

**Imagens**
- [ ] Arquivo `.jpg` que não é imagem → recusado
- [ ] PNG renomeado para `.jpg` → aceito e gravado com extensão `.png`
- [ ] Imagem de 3,1 MB → recusada; GIF → recusado
- [ ] Nome gravado = `projetos/<uuid>.<ext>`, sem o nome original
- [ ] Sétima imagem extra → recusada pelo formset

**Moderação**
- [ ] Publicar em lote: projeto completo vira `publicado` com `publicado_em`; projeto sem capa fica em `em_revisao` e aparece na mensagem
- [ ] Devolver sem `motivo_ajustes` → não muda; com motivo → `ajustes`
- [ ] Republicar não altera `publicado_em`
- [ ] Usuário anônimo no admin → login (G15)

**Importação**
- [ ] CSV com `;` e com `,`, com e sem BOM → mesmo resultado
- [ ] Sem `--aplicar` → nada gravado e relatório completo
- [ ] Uma linha com erro → nada gravado, mesmo com `--aplicar`; relatório aponta a linha e o motivo
- [ ] Rodar duas vezes o mesmo CSV → nenhum projeto duplicado
- [ ] Projeto já reivindicado → "ignorado", RA não muda
- [ ] Linha "EXEMPLO" ignorada; turma inexistente → erro
- [ ] O RA não aparece na saída do comando em nenhum caso (teste captura a saída)
- [ ] Testes do caminho crítico passando

## Perguntas em aberto
Não bloqueiam a implementação:
- **Etec (coordenação)**: cursos e turmas participantes; se o técnico é
  "módulo" ou "semestre"; regra para menores (hoje: só primeiro nome,
  sem foto de pessoas).
- Prazo de edição desta edição: proposta 20/10, 23h59 (antes do pré-ensaio).
