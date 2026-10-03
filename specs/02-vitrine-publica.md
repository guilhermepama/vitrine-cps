# Spec — Vitrine pública e área do grupo

- **Responsável**: Cleiton (@gustimmolp)
- **Status**: rascunho (aguardando revisão do coordenador)
- **Depende de**: ADR-002 (stack), ADR-006 (R2), ADR-009 (cadastro pelo
  grupo), spec 01 (models e `cadastro/seguranca.py`), spec 00 (esqueleto)

## Objetivo
Entregar as duas telas que ficam na frente do cadastro: a **área do grupo**,
onde o representante reivindica o projeto com o RA e o edita por um link
secreto, e a **vitrine pública**, a página permanente de cada projeto
aprovado, que divulga o evento e **não** tem caminho de voto.

## Escopo

### Área do grupo
- Página `/grupo/` com o formulário de reivindicação: o representante informa
  o RA e, se ele bate com um projeto elegível, o sistema mostra o **link de
  edição uma única vez**.
- Rate limit na reivindicação (RAs são sequenciais e enumeráveis) e
  resposta genérica para qualquer RA que não resulte em link.
- Página de edição `/grupo/editar/<token>/`: formulário com título, resumo,
  descrição, componente de origem, links, capa, equipe (integrantes) e
  imagens extras. Ao salvar, o projeto vai para `em_revisao`.
- Mensagem do admin (`motivo_ajustes`) exibida ao grupo quando o projeto
  está em `ajustes`.
- Lista "o que falta para a publicação" na página de edição (capa, resumo,
  descrição, ao menos 1 integrante — as mesmas exigências do "Publicar" da
  spec 01).
- Modo somente leitura quando o prazo de edição acabou ou o projeto já está
  `publicado`.

### Vitrine pública
- Página `/projeto/<slug>/`, template único para todos os projetos, só para
  projetos `publicado`.
- Meta tags Open Graph e Twitter Card — a prévia no WhatsApp é o canal de
  divulgação.
- Convite para o evento (data vinda da `Edicao`) e um botão que leva a uma
  página de explicação do voto presencial, `/como-votar/` (guardrail 8).
- Template base mobile-first, com a identidade visual entregue pelo
  coordenador.

## Fora de escopo
- Models, migrations, admin, importação da lista, moderação, regerar e
  revogar link (spec 01). Esta spec **usa** `Projeto`, `Integrante`,
  `ImagemProjeto` e `cadastro/seguranca.py`; não os altera.
- Qualquer mudança em `settings.py`, `config/urls.py` ou em models do
  `cadastro` (são do coordenador — peça).
- Login de aluno, senha, recuperação de acesso, envio do link por e-mail.
- Cédula, tokens de voto, estações, visitantes (spec 03).
- Ranking, notas e a nota composta (specs 04 e 06): a vitrine não exibe
  votos, notas nem colocação.
- Página-índice com a lista de todos os projetos (ver pergunta 6).
- Busca, filtros, comentários, curtidas, compartilhamento por botões.
- Fotos de pessoas, redimensionar ou converter imagens, editor de texto
  rico (a descrição é texto simples).
- Edição do `slug` ou do `representante_nome` pelo grupo.

## Comportamento esperado

### Reivindicar o projeto (`/grupo/`)
- Quando o representante abre `/grupo/`, o sistema exibe o formulário (campo
  RA e a explicação de que o link aparece **uma vez** e deve ser guardado).
- Quando envia o RA, o sistema: (1) valida o formato com
  `cadastro.seguranca.hash_ra`, que recusa (`ValueError`) o que não tiver
  5 a 20 dígitos depois de remover espaço, ponto, hífen e barra — formato
  inválido vira erro de formulário e **não consulta o banco**; (2) checa o
  rate limit; (3) calcula o hash; (4) busca o projeto com esse `ra_hmac`,
  `reivindicado_em` nulo, `status = pre_cadastrado` e
  `turma.edicao.ativa = true`. Como o model garante um RA por projeto em
  cada edição, a busca devolve no máximo um.
- Quando encontra, **numa transação com lock da linha** (`select_for_update`)
  e conferindo de novo que `reivindicado_em` continua nulo: grava
  `reivindicado_em` e gera o link com `Projeto.regerar_link()` (que grava o
  hash e `token_edicao_gerado_em` e devolve o token em claro), e responde
  **na mesma resposta do POST** (sem redirecionar) mostrando o link
  completo, com aviso "guarde este link, ele não será exibido de novo". A
  resposta leva `Cache-Control: no-store`.
- Quando dois requests tentam reivindicar o mesmo projeto ao mesmo tempo,
  só um recebe o link; o outro recebe a resposta genérica.
- Quando o RA não existe, já foi reivindicado, é de outra edição ou o
  projeto não está `pre_cadastrado`, o sistema responde **a mesma página,
  com o mesmo status e o mesmo texto**: "Não encontramos um projeto
  disponível para este RA. Confira se digitou o RA igual ao da sua
  matrícula. Se acha que é um erro, procure a coordenação." Nunca diz qual
  regra barrou.
- Quando o RA recarrega a página de resposta do POST (reenvio), cai na
  resposta genérica, porque o projeto já foi reivindicado. A página avisa
  que link perdido só o admin regera.
- Quando o limite de falhas estoura, responde 429 com "Muitas tentativas.
  Tente de novo em alguns minutos." — sem indicar se algum RA existe.
- O RA em claro nunca é gravado, logado, repetido na resposta nem colocado
  em mensagem de erro; o campo só é lido do POST e passado a `hash_ra`.

#### Rate limit (guardrail 7, por analogia)
- Conta **só falhas** (resposta genérica), no cache do Django (cache em
  banco, compartilhado entre workers — `settings.py`):
  - por IP, **generoso**: **50 falhas em 10 min**;
  - global: **200 falhas por hora** (proteção contra varredura distribuída,
    não depende de IP).
- Sucesso não consome limite. O Wi-Fi da faculdade sai por um único IP e
  uma turma inteira reivindica ao mesmo tempo, então o limite por IP só
  barra script — a mesma lógica da spec 03. Identificar o aparelho pelo
  MAC não é possível: ele não chega ao servidor (o roteador o substitui) e
  os celulares usam MAC aleatório.
- Estourou o limite → 429 até a janela passar; o contador não é zerado por
  um acerto.
- O IP só existe como chave do cache, **com expiração** e transformado em
  hash com segredo (ADR-003, complemento): nunca em log nem em tabela de
  model. Atrás do proxy, o IP vem do cabeçalho que a ADR-006 definir; o
  nome fica numa constante única (como na spec 03), e o contador usa
  `CACHES["default"]` (cache em banco, compartilhado entre os workers).
  O `incr` do `DatabaseCache` não é atômico: o limite é barreira contra
  abuso, não contagem exata.
- Os números são proposta (pergunta 3); ficam em constantes no módulo, não
  espalhados.

### Editar pelo link (`/grupo/editar/<token>/`)
- Quando o token não existe, foi revogado/regerado ou está malformado, o
  sistema responde **404 genérico**, igual nos três casos. A busca é por
  `token_edicao_hash = hash_token(token)`, confirmada com `token_confere`.
- Quando o projeto está `pre_cadastrado`, `em_revisao` ou `ajustes`, o
  prazo (`Edicao.edicao_aberta()`) está aberto e a votação ainda não foi
  aberta (`Edicao.votacao_foi_aberta()` falso), `GET` mostra o formulário
  preenchido. Em `ajustes`, mostra o `motivo_ajustes` no topo. Projeto da
  Etec mostra a orientação "não envie fotos de pessoas" (a conferência é
  humana, na moderação — spec 01).
- Quando o grupo salva um formulário válido: grava os campos, os
  integrantes (1–10) e as imagens (capa + até 6 extras) numa transação;
  muda `pre_cadastrado` ou `ajustes` para `em_revisao` (em `em_revisao`
  permanece); mostra confirmação "Enviado para revisão da coordenação".
  Salvar com campos faltando é permitido (rascunho): o status vira
  `em_revisao` e a lista "o que falta", vinda de
  `Projeto.pendencias_para_publicar()`, continua visível. O status muda
  **só por `save()` na instância**, nunca por `update()`, porque as travas
  da spec 01 vivem no `save()`.
- Quando o `save()` recusa a gravação com `ValidationError` (por exemplo,
  a votação foi aberta no meio do envio), o sistema desfaz a transação,
  não grava nada e responde como "edição encerrada" (403).
- Quando o formulário é inválido (tamanho, URL que não seja `https://`,
  integrante da Etec com mais de uma palavra no nome, imagem inválida, 7ª
  imagem extra, 11º integrante), responde 400 com o formulário e
  mensagens de erro genéricas por campo; nada é gravado. Integrantes da
  Fatec aceitam nome completo.
- Quando o prazo acabou, a votação já foi aberta **ou** o projeto está
  `publicado`, `GET` mostra o conteúdo em somente leitura, e `POST`
  responde 403 com a mesma explicação ("edição encerrada; fale com a
  coordenação"). Nada é gravado.
- Quando o admin regera ou revoga o link, o link antigo passa a dar 404 na
  hora (a página consulta o hash a cada request).
- Dois colegas com o mesmo link editando ao mesmo tempo: vale a última
  gravação (aceito; o link é de uma pessoa só).
- Páginas do grupo respondem com `Referrer-Policy: no-referrer`,
  `X-Robots-Tag: noindex` e `Cache-Control: no-store`, para o token na URL
  não vazar por referência, buscador ou cache.
- Upload: tipo real, 3 MB e nome gerado pelo servidor vêm de
  `cadastro.imagens` (`validar_imagem`, G14), e os limites vêm de
  `Integrante.MAXIMO_POR_PROJETO` (10) e `ImagemProjeto.MAXIMO_POR_PROJETO`
  (6); aqui são aplicados no formulário e nos formsets do grupo (a spec 01
  deixa o teste do formulário do grupo para esta spec). O arquivo original
  nunca é usado como nome.

### Página pública (`/projeto/<slug>/`)
- Quando o `slug` não existe **ou** o projeto não está `publicado`, o sistema
  responde o mesmo 404 (não revela projetos em revisão).
- Quando o projeto está `publicado`, a página mostra: capa, título, curso
  e período (rótulo da turma), componente de origem (se houver), resumo,
  descrição (texto simples, quebras de linha preservadas, **escapado**),
  equipe (nome e papel, como gravados), links externos e galeria.
- Links externos abrem com `rel="noopener noreferrer nofollow"`; só
  `https://`. Imagens da galeria usam a legenda como texto alternativo.
- A página **não** depende da edição ativa: o link é permanente e continua
  valendo em edições seguintes.
- Meta tags: `og:title` (título), `og:description` (resumo), `og:image`
  (capa, URL absoluta `https`), `og:url` (URL canônica absoluta),
  `og:type=website`, `og:locale=pt_BR`, `twitter:card=summary_large_image`.
  `<title>`: "Título — Vitrine CPS".
- Bloco de convite: "Conheça este projeto no evento — [data] na [local]"
  e botão "Quero votar" que aponta **só** para `/como-votar/`.
- `/como-votar/`: página estática que explica que a votação é presencial,
  como funciona o credenciamento por QR nas estações e que o link público
  não vota. Nenhum formulário, nenhum botão de voto.
- Nenhum link, formulário ou script da vitrine aponta para `/entrar`,
  `/estacao`, `/votar`, `/votos` ou `/visitantes` (G8).
- Dado pessoal na página pública: apenas o que está em `Integrante` e no
  texto do projeto. `representante_nome`, `ra_hmac`, tokens e e-mails
  nunca aparecem.

## Dados
Esta spec **não cria tabelas nem migrations** (as migrations estão na spec 01).

Lê: `Edicao` (ativa, `data_evento`, `edicao_aberta()`), `Curso`, `Turma`
(`rotulo`), `Projeto`, `Integrante`, `ImagemProjeto`.

Escreve, somente nestes campos:
- `Projeto`: `titulo`, `resumo`, `descricao`, `componente_origem`, `capa`,
  `link_repositorio`, `link_demo`, `link_video`, `status` (só
  `pre_cadastrado`/`ajustes` → `em_revisao`), `reivindicado_em`,
  `token_edicao_hash`, `token_edicao_gerado_em`.
- `Integrante` e `ImagemProjeto`: criar, alterar, remover e reordenar os do
  próprio projeto.

Nunca escreve: `slug`, `ra_hmac`, `representante_nome`, `publicado_em`,
`motivo_ajustes`, `turma`. Usa o cache do Django só para os contadores do
rate limit.

Regra da spec 01 para quem usa os models: nos campos travados (`status`,
`slug`, `turma`) a escrita é **só por `save()` na instância ou pelos métodos
do model**, nunca por `QuerySet.update()` ou `bulk_update()`. O
`/revisar-pr` confere isso.

Lógica de negócio fica em `vitrine/servicos.py` (reivindicar, salvar
edição, rate limit), fora das views, para ser testada sem HTTP.

## Endpoints / telas
| Método | Rota | Entrada | Saída | Erros |
|---|---|---|---|---|
| GET | `/projeto/<slug>/` | — | HTML da vitrine + Open Graph | 404 (inexistente ou não publicado) |
| GET | `/como-votar/` | — | HTML estático | — |
| GET | `/grupo/` | — | formulário de RA | — |
| POST | `/grupo/` | `ra` | link de edição (1 vez) ou resposta genérica | 400 formato inválido; 429 rate limit |
| GET | `/grupo/editar/<token>/` | — | formulário, ou leitura se encerrado/publicado | 404 token inválido |
| POST | `/grupo/editar/<token>/` | campos do projeto + formsets (multipart) | confirmação | 400 validação; 403 encerrado/publicado; 404 token inválido |

Rotas em `vitrine/urls.py` (`app_name = "vitrine"`); o include raiz já
existe. CSRF ligado nos POSTs. Templates em `vitrine/templates/vitrine/`,
estáticos em `vitrine/static/vitrine/`.

## Guardrails aplicáveis
3 (por analogia: nenhum segredo no código ou na resposta), 7 (por analogia:
rate limit na reivindicação), 8, 11 (por analogia: RA e token nunca em log,
resposta de erro ou página pública), 12, 13, 14, 17.

Reler antes de implementar: 8 (nenhum caminho de voto na vitrine), 12
(validar toda entrada, erro genérico), 13 (só ORM) e 14 (upload).

## Critérios de aceite

**Reivindicação**
- [ ] RA válido de projeto `pre_cadastrado` da edição ativa → mostra o link e grava `reivindicado_em`, hash do token e `token_edicao_gerado_em`; o token em claro não está no banco
- [ ] RA inexistente, RA já reivindicado e RA de outra edição → respostas **idênticas** (status e corpo)
- [ ] Recarregar o POST após o sucesso → resposta genérica, não um segundo link
- [ ] 2 POSTs simultâneos com o mesmo RA → um link emitido, um genérico
- [ ] 50 falhas do mesmo IP em 10 min passam; a 51ª → 429; sucesso não conta
- [ ] 200 falhas somadas de IPs diferentes em 1 hora passam; a 201ª → 429 para qualquer IP
- [ ] RA vazio, com letra ou fora de 5–20 dígitos → erro de formulário, sem consulta de RA; `123.456-7` e `1234567` reivindicam o mesmo projeto
- [ ] A chave do IP no cache expira em 10 min e não contém o IP em claro; o IP não aparece em log nem em tabela de model
- [ ] O RA em claro não aparece no log, na resposta de erro nem no banco (teste captura log e resposta)
- [ ] Resposta do link tem `Cache-Control: no-store`

**Edição**
- [ ] Token inexistente, revogado e regerado → mesmo 404; o link antigo para de valer após "regerar"
- [ ] Salvar completo em `pre_cadastrado` ou `ajustes` → `em_revisao` e dados gravados; `slug` inalterado mesmo mudando o título
- [ ] Salvar incompleto é aceito e a lista "o que falta" mostra os itens pendentes
- [ ] Prazo encerrado → `GET` somente leitura, `POST` 403, nada gravado
- [ ] Projeto `publicado` → `POST` 403, nada gravado
- [ ] Votação da edição já aberta → `GET` somente leitura, `POST` 403, nada gravado; `ValidationError` do `save()` no meio do envio → transação desfeita, nada gravado
- [ ] Em `ajustes`, o `motivo_ajustes` aparece ao grupo
- [ ] Link com `http://` ou `javascript:` → recusado; integrante de projeto da Etec com duas palavras → recusado; o mesmo nome em projeto da Fatec → aceito
- [ ] Nenhum `update()` ou `bulk_update()` em `status`, `slug` ou `turma` no app `vitrine` (revisão de código)
- [ ] 7ª imagem extra, 11º integrante, arquivo `.jpg` que não é imagem e imagem > 3 MB → recusados, nada gravado
- [ ] Nome do arquivo gravado = `projetos/<uuid>.<ext>`, sem o nome original
- [ ] Páginas do grupo respondem com `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex` e `Cache-Control: no-store`

**Vitrine pública**
- [ ] Projeto `publicado` → 200 com título, resumo, descrição, equipe, links e galeria
- [ ] Slug inexistente e projeto `em_revisao`, `ajustes` ou `pre_cadastrado` → 404 idêntico
- [ ] HTML contém `og:title`, `og:description`, `og:image` (URL absoluta https), `og:url` e `twitter:card`
- [ ] Descrição com `<script>` aparece escapada, sem executar
- [ ] O HTML da vitrine e de `/como-votar/` não contém nenhum link ou formulário para `/entrar`, `/estacao`, `/votar`, `/votos` ou `/visitantes` (teste automático, G8)
- [ ] O HTML não contém `representante_nome`, RA nem token
- [ ] Projeto publicado numa edição anterior continua acessível
- [ ] Página legível em 360 px de largura, sem rolagem horizontal
- [ ] Testes do caminho crítico passando (`pytest`), CI verde

**Fatiamento sugerido (PRs até ~300 linhas, sem migrations e testes)**
1. `vitrine: reivindicação por RA` — serviço, rate limit, `/grupo/` (10/10)
2. `vitrine: edição pelo link` — formulário, formsets, upload (10/10)
3. `vitrine: página pública e Open Graph` — `/projeto/<slug>/`, `/como-votar/`, template base (12/10)

## Perguntas em aberto
Dúvidas para o coordenador, **antes** de implementar:

1. **Editar em `em_revisao`.** Proposta: o grupo pode editar enquanto o
   projeto está `em_revisao` (corrige antes da aprovação); a tabela de
   status da spec 01 só descreve a ida `pre_cadastrado`/`ajustes` →
   `em_revisao`. Confirma?
2. **Link e logs.** O token de edição vai no caminho da URL
   (`/grupo/editar/<token>/`), e o log de acesso do servidor pode
   registrá-lo (G11 vale por analogia). O critério de escolha do servidor
   (ADR-006, até 08/10) já pede tirar o log de acesso das rotas do
   visitante: pode incluir `/grupo/editar/`? Se não, aceitamos o risco
   (o admin revoga o link) ou trocamos o token por sessão no primeiro
   acesso — mais código, só vale a pena se o servidor logar URLs.
3. **Números do rate limit** (50 falhas/10 min por IP, 200/hora global).
   O limite por IP é generoso porque a turma toda sai pelo mesmo IP do
   Wi-Fi da faculdade (ajustado a partir de uma proposta inicial de 10).
   Risco aceito: quem acertar um RA por tentativa consome a reivindicação
   do colega — o admin regera o link, e nada fica público sem aprovação.
   O limite global pode, em ataque, travar reivindicações legítimas por
   até 1 hora. Aceitável?
4. **Local e horário do evento.** O convite precisa de local e horário;
   `Edicao` só tem `data_evento`. Escrevo o local fixo no template (Fatec
   Olímpia) ou o Guilherme adiciona campos à `Edicao`?
5. **Identidade visual.** O `03-estado.md` prevê para 05/10. Até lá, o
   template usa CSS neutro e variáveis CSS para trocar depois. Entra como
   arquivos no repositório (onde?) ou como um guia de cores e logo?
6. **Página-índice dos projetos.** O escopo atual só tem a página de cada
   projeto. Uma listagem `/projetos/` (por turma) entra nesta edição ou
   fica para depois de 12/10?
7. **Tamanho da requisição.** Uma edição com capa + 6 extras pode chegar
   a ~21 MB num POST. O servidor/proxy escolhido (ADR-006, até 08/10)
   aceita corpo desse tamanho?
8. **Nome da chave do IP.** Se a spec 03 expuser uma função compartilhada
   para transformar o IP em chave de cache (hash com segredo), uso a mesma
   em vez de duplicar. O Renan confirma o nome e o app dela?

### Já respondidas pela spec 01 (e pelo código na `main`)
- `cadastro.seguranca` já tem `hash_token(token)`, `token_confere` e
  `normalizar_ra` (5–20 dígitos): uso essas funções, não crio outras.
- Gravar a reivindicação e o status fica em `vitrine/servicos.py`, usando
  `save()` na instância e `Projeto.regerar_link()`; nunca `update()`.
- Equipe: Etec só primeiro nome, Fatec nome completo, validado em
  `Integrante.clean()`; a vitrine mostra o nome como gravado. Se a
  coordenação decidir outra regra, a mudança é só nesse `clean()`.
- Depois de aberta a votação, status e turma não mudam: a tela do grupo
  vira somente leitura nesse caso.
