# Spec — Vitrine pública e área do grupo

- **Responsável**: Cleiton (@gustimmolp)
- **Status**: rascunho (parecer do coordenador no PR #23 incorporado; aguardando nova revisão)
- **Depende de**: ADR-002 (stack), ADR-006 (R2, servidor), ADR-009 (cadastro
  pelo grupo), spec 01 (models e `cadastro/seguranca.py`, incluindo
  `ip_do_cliente` e `chave_ip` do PR #25), spec 00 (esqueleto)

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
- Página de edição `/grupo/editar/<token>/` com dois botões: **"Salvar"**
  (guarda o rascunho e **mantém o status**) e **"Enviar para revisão"**
  (só ativo quando não há pendências; muda o status para `em_revisao`).
  Campos: título, resumo, descrição, componente de origem, links e equipe
  (integrantes).
- **Imagens enviadas uma a uma**, em requisições próprias: capa e até 6
  imagens extras, com legenda opcional, e remoção individual.
- Mensagem do admin (`motivo_ajustes`) exibida ao grupo quando o projeto
  está em `ajustes`.
- Lista "o que falta para a publicação" na página de edição, vinda de
  `Projeto.pendencias_para_publicar()` (capa, resumo, descrição, ao menos 1
  integrante — as mesmas exigências do "Publicar" da spec 01).
- Modo somente leitura quando o projeto está `em_revisao` ou `publicado`,
  o prazo de edição acabou ou a votação foi aberta.

### Vitrine pública
- Página `/projeto/<slug>/`, template único para todos os projetos, só para
  projetos `publicado`.
- Meta tags Open Graph e Twitter Card — a prévia no WhatsApp é o canal de
  divulgação.
- Convite para o evento, com data vinda da `Edicao` e **local e horário em
  texto fixo no template** (nesta edição, sem campo novo), e um botão que
  leva a uma página de explicação do voto presencial, `/como-votar/`
  (guardrail 8).
- Templates das páginas desta spec, herdando o **`base.html` do projeto**
  (criado pelo coordenador, na pasta `templates/` da raiz, com as variáveis
  de CSS e o logo SVG em `static/` do projeto), mobile-first.

## Fora de escopo
- Models, migrations, admin, importação da lista, moderação, regerar e
  revogar link (spec 01). Esta spec **usa** `Projeto`, `Integrante`,
  `ImagemProjeto` e `cadastro/seguranca.py`; não os altera.
- Qualquer mudança em `settings.py`, `config/urls.py`, em models do
  `cadastro`, no `base.html` ou na pasta `static/` do projeto (são do
  coordenador — peça).
- Login de aluno, senha, recuperação de acesso, envio do link por e-mail.
- Cédula, tokens de voto, estações, visitantes (spec 03).
- Ranking, notas e a nota composta (specs 04 e 06): a vitrine não exibe
  votos, notas nem colocação.
- Página-índice `/projetos/` com a lista de todos os projetos: fica fora do
  prazo de 12/10; fatia pequena depois de 13/10, se houver folga.
- Busca, filtros, comentários, curtidas, compartilhamento por botões.
- Fotos de pessoas, redimensionar ou converter imagens (inclusive
  miniatura da capa), editor de texto rico (a descrição é texto simples).
- Edição do `slug` ou do `representante_nome` pelo grupo.
- Retirar o projeto de `em_revisao` pelo próprio grupo: quem precisa
  corrigir fala com a coordenação, que devolve para ajustes.

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
  `turma.edicao.ativa = true`, cuja edição ainda aceita edição
  (`Edicao.edicao_aberta()` verdadeiro e `votacao_foi_aberta()` falso).
  Como o model garante um RA por projeto em cada edição, a busca devolve
  no máximo um.
- Quando encontra, **numa transação com lock da linha** (`select_for_update`)
  e conferindo de novo que `reivindicado_em` continua nulo: grava
  `reivindicado_em` e gera o link com `Projeto.regerar_link()` (que grava o
  hash e `token_edicao_gerado_em` e devolve o token em claro), e responde
  **na mesma resposta do POST** (sem redirecionar) mostrando o link
  completo, com aviso "guarde este link, ele não será exibido de novo". A
  resposta leva `Cache-Control: no-store`.
- Quando dois requests tentam reivindicar o mesmo projeto ao mesmo tempo,
  só um recebe o link; o outro recebe a resposta genérica.
- Quando o RA não existe, já foi reivindicado, é de outra edição, o
  projeto não está `pre_cadastrado` **ou o prazo de edição já acabou (ou a
  votação já abriu)**, o sistema responde **a mesma página, com o mesmo
  status e o mesmo texto**: "Não encontramos um projeto disponível para este
  RA. Confira se digitou o RA igual ao da sua matrícula. Se acha que é um
  erro, procure a coordenação." Nunca diz qual regra barrou.
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
  - global: **1.000 falhas por hora** (proteção contra varredura
    distribuída, não depende de IP). Um limite global baixo seria uma
    arma: um único script o esgotaria e travaria a reivindicação da turma
    inteira; o dano de uma enumeração é recuperável (o admin regera o
    link, e nada fica público sem aprovação), o de um bloqueio geral não.
- Sucesso não consome limite. O Wi-Fi da faculdade sai por um único IP e
  uma turma inteira reivindica ao mesmo tempo, então o limite por IP só
  barra script — a mesma lógica da spec 03. Identificar o aparelho pelo
  MAC não é possível: ele não chega ao servidor (o roteador o substitui) e
  os celulares usam MAC aleatório.
- Estourou o limite → 429 até a janela passar; o contador não é zerado por
  um acerto.
- **IP**: sempre por `cadastro.seguranca.ip_do_cliente(request)` e
  `chave_ip(ip)` (HMAC com `IP_HMAC_SECRET`, IPv6 reduzido ao /64). O
  código **nunca lê `REMOTE_ADDR` nem `X-Forwarded-For` diretamente**: o
  cabeçalho do IP real é a variável `DJANGO_IP_HEADER`, do coordenador. O
  IP em claro não vai para cache, log nem tabela de model; só a chave com
  prefixo do app (`rl:grupo:ip:<chave>`, expiração de 10 min) entra no
  cache. A chave global é `rl:grupo:global` (expiração de 1 h).
- O `incr` do `DatabaseCache` não é atômico: o limite é barreira contra
  abuso, não contagem exata.
- Os números ficam em constantes no módulo, não espalhados.

### Editar pelo link (`/grupo/editar/<token>/`)
- Quando o token não existe, foi revogado/regerado ou está malformado, o
  sistema responde **404 genérico**, igual nos três casos. A busca é por
  `token_edicao_hash = hash_token(token)`, confirmada com `token_confere`.
  Toda requisição desta seção (formulário, imagem, remoção) repete essa
  busca e as checagens abaixo.
- **Editável** = status `pre_cadastrado` ou `ajustes`, prazo
  (`Edicao.edicao_aberta()`) aberto e votação ainda não aberta
  (`Edicao.votacao_foi_aberta()` falso). Nesse caso, `GET` mostra o
  formulário preenchido. Em `ajustes`, mostra o `motivo_ajustes` no topo.
  Projeto da Etec mostra a orientação "não envie fotos de pessoas" (a
  conferência é humana, na moderação — spec 01).
- Quando o grupo clica em **"Salvar"** com formulário válido: grava os
  campos e os integrantes (1–10) numa transação e **mantém o status**;
  mostra "Rascunho salvo" e a lista "o que falta". Salvar com campos
  faltando é permitido.
- O botão **"Enviar para revisão"** só vem ativo quando
  `pendencias_para_publicar()` está vazio (estado gravado), mas o servidor
  **não confia no botão**: ao receber `acao=enviar`, grava os campos,
  confere as pendências no estado gravado e só então muda `pre_cadastrado`
  ou `ajustes` para `em_revisao`, tudo na mesma transação. Com pendências,
  responde 400, desfaz tudo, mostra o formulário com o que o grupo digitou e
  a lista do que falta. Sucesso mostra "Enviado para revisão da
  coordenação". O status muda **só por `save()` na instância**, nunca por
  `update()`, porque as travas da spec 01 vivem no `save()`.
- Quando o `save()` recusa a gravação com `ValidationError` (por exemplo,
  a votação foi aberta no meio do envio), o sistema desfaz a transação,
  não grava nada e responde como "edição encerrada" (403).
- Quando o formulário é inválido (tamanho, URL que não seja `https://`,
  integrante da Etec com mais de uma palavra no nome, 11º integrante),
  responde 400 com o formulário e mensagens de erro genéricas por campo;
  nada é gravado. Integrantes da Fatec aceitam nome completo.
- Quando o projeto **não é editável** (`em_revisao`, `publicado`, prazo
  encerrado ou votação aberta), `GET` mostra o conteúdo em somente
  leitura, e qualquer `POST` responde 403 com a explicação ("edição
  encerrada; fale com a coordenação"). Nada é gravado.
- Quando o admin regera ou revoga o link, o link antigo passa a dar 404 na
  hora (a página consulta o hash a cada request).
- Dois colegas com o mesmo link editando ao mesmo tempo: vale a última
  gravação (aceito; o link é de uma pessoa só).
- Páginas do grupo respondem com `Referrer-Policy: no-referrer`,
  `X-Robots-Tag: noindex` e `Cache-Control: no-store`, para o token na URL
  não vazar por referência, buscador ou cache. O token fica na URL (não é
  trocado por sessão); o coordenador inclui `/grupo/editar/` no critério
  de logs da hospedagem (ADR-006).

### Imagens, uma por requisição
- `POST .../imagem/` recebe **um** arquivo (`arquivo`), o `tipo` (`capa` ou
  `extra`) e a `legenda` opcional. Nenhuma requisição leva mais de uma
  imagem, então o corpo máximo é o de uma imagem de 3 MB mais o formulário.
- `tipo=capa` grava (ou substitui) `Projeto.capa`. O arquivo antigo pode
  ficar órfão no bucket (aceito: não há limpeza nesta edição). `tipo=extra`
  cria uma `ImagemProjeto`; a 7ª extra é recusada.
- `POST .../imagem/<id>/remover/` remove uma imagem extra **do próprio
  projeto**; `<id>` de outro projeto responde 404.
- Tipo real, 3 MB e nome gerado pelo servidor vêm de `cadastro.imagens`
  (`validar_imagem`, G14); o limite de 6 vem de
  `ImagemProjeto.MAXIMO_POR_PROJETO` e o de 10 integrantes de
  `Integrante.MAXIMO_POR_PROJETO`. O arquivo original nunca é usado como
  nome. Imagem inválida ou grande demais → 400, nada gravado.
- As mesmas regras de "editável" valem: fora dela, 403 e nada é gravado.
- O servidor da hospedagem precisa aceitar corpo de pelo menos 4 MB por
  requisição (ver pergunta 1).

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
- Bloco de convite: "Conheça este projeto no evento — [data da `Edicao`],
  [local e horário em texto fixo]" e botão "Quero votar" que aponta **só**
  para `/como-votar/`.
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

Lê: `Edicao` (ativa, `data_evento`, `edicao_aberta()`,
`votacao_foi_aberta()`), `Curso`, `Turma` (`rotulo`), `Projeto`,
`Integrante`, `ImagemProjeto`.

Escreve, somente nestes campos:
- `Projeto`: `titulo`, `resumo`, `descricao`, `componente_origem`, `capa`,
  `link_repositorio`, `link_demo`, `link_video`, `status` (só
  `pre_cadastrado`/`ajustes` → `em_revisao`, e só em "Enviar para
  revisão"), `reivindicado_em`, `token_edicao_hash`,
  `token_edicao_gerado_em`.
- `Integrante` e `ImagemProjeto`: criar, alterar, remover e reordenar os do
  próprio projeto.

Nunca escreve: `slug`, `ra_hmac`, `representante_nome`, `publicado_em`,
`motivo_ajustes`, `turma`. Usa o cache do Django só para os contadores do
rate limit.

Regra da spec 01 para quem usa os models: nos campos travados (`status`,
`slug`, `turma`) a escrita é **só por `save()` na instância ou pelos métodos
do model**, nunca por `QuerySet.update()` ou `bulk_update()`. O
`/revisar-pr` confere isso.

Lógica de negócio fica em `vitrine/servicos.py` (reivindicar, salvar,
enviar para revisão, imagens, rate limit), fora das views, para ser
testada sem HTTP.

## Endpoints / telas
| Método | Rota | Entrada | Saída | Erros |
|---|---|---|---|---|
| GET | `/projeto/<slug>/` | — | HTML da vitrine + Open Graph | 404 (inexistente ou não publicado) |
| GET | `/como-votar/` | — | HTML estático | — |
| GET | `/grupo/` | — | formulário de RA | — |
| POST | `/grupo/` | `ra` | link de edição (1 vez) ou resposta genérica | 400 formato inválido; 429 rate limit |
| GET | `/grupo/editar/<token>/` | — | formulário, ou leitura se não editável | 404 token inválido |
| POST | `/grupo/editar/<token>/` | campos + integrantes + `acao` (`salvar` ou `enviar`) | confirmação | 400 validação ou pendências; 403 não editável; 404 token inválido |
| POST | `/grupo/editar/<token>/imagem/` | `arquivo` (1), `tipo`, `legenda?` (multipart) | página de edição atualizada | 400 imagem inválida ou 7ª extra; 403 não editável; 404 token inválido |
| POST | `/grupo/editar/<token>/imagem/<id>/remover/` | — | página de edição atualizada | 403 não editável; 404 token ou imagem inválidos |

Rotas em `vitrine/urls.py` (`app_name = "vitrine"`); o include raiz já
existe. CSRF ligado nos POSTs. Templates em `vitrine/templates/vitrine/`,
herdando o `base.html` do projeto.

## Guardrails aplicáveis
3 (por analogia: nenhum segredo no código ou na resposta), 7 (por analogia:
rate limit na reivindicação), 8, 11 (por analogia: RA, token e IP nunca em
log, resposta de erro ou página pública), 12, 13, 14, 17.

Reler antes de implementar: 8 (nenhum caminho de voto na vitrine), 12
(validar toda entrada, erro genérico), 13 (só ORM) e 14 (upload).

## Critérios de aceite

**Reivindicação**
- [ ] RA válido de projeto `pre_cadastrado` da edição ativa → mostra o link e grava `reivindicado_em`, hash do token e `token_edicao_gerado_em`; o token em claro não está no banco
- [ ] RA inexistente, RA já reivindicado, RA de outra edição e RA depois do prazo de edição (ou com a votação aberta) → respostas **idênticas** (status e corpo)
- [ ] Recarregar o POST após o sucesso → resposta genérica, não um segundo link
- [ ] 2 POSTs simultâneos com o mesmo RA → um link emitido, um genérico
- [ ] 50 falhas do mesmo IP em 10 min passam; a 51ª → 429; sucesso não conta
- [ ] 1.000 falhas somadas de IPs diferentes em 1 hora passam; a 1.001ª → 429 para qualquer IP
- [ ] Dois endereços IPv6 do mesmo /64 contam como o mesmo IP
- [ ] RA vazio, com letra ou fora de 5–20 dígitos → erro de formulário, sem consulta de RA; `123.456-7` e `1234567` reivindicam o mesmo projeto
- [ ] A chave do IP no cache vem de `chave_ip(ip_do_cliente(request))`, expira em 10 min e não contém o IP em claro; o IP não aparece em log nem em tabela de model; o app `vitrine` não lê `REMOTE_ADDR` nem `X-Forwarded-For` (revisão de código)
- [ ] O RA em claro não aparece no log, na resposta de erro nem no banco (teste captura log e resposta)
- [ ] Resposta do link tem `Cache-Control: no-store`

**Edição**
- [ ] Token inexistente, revogado e regerado → mesmo 404; o link antigo para de valer após "regerar"
- [ ] "Salvar" em `pre_cadastrado` ou `ajustes` grava os dados e **mantém o status**, mesmo incompleto; `slug` inalterado mesmo mudando o título
- [ ] "Enviar para revisão" sem pendências → `em_revisao` e dados gravados
- [ ] "Enviar para revisão" com pendências (ex.: capa ausente, ou resumo apagado no mesmo envio) → 400, **nada gravado**, formulário volta com o digitado e a lista do que falta
- [ ] Projeto `em_revisao` → `GET` somente leitura, `POST` 403, nada gravado
- [ ] Prazo encerrado → `GET` somente leitura, `POST` 403, nada gravado
- [ ] Projeto `publicado` → `POST` 403, nada gravado
- [ ] Votação da edição já aberta → `GET` somente leitura, `POST` 403, nada gravado; `ValidationError` do `save()` no meio do envio → transação desfeita, nada gravado
- [ ] Em `ajustes`, o `motivo_ajustes` aparece ao grupo
- [ ] Link com `http://` ou `javascript:` → recusado; integrante de projeto da Etec com duas palavras → recusado; o mesmo nome em projeto da Fatec → aceito; 11º integrante → recusado
- [ ] Nenhum `update()` ou `bulk_update()` em `status`, `slug` ou `turma` no app `vitrine` (revisão de código)
- [ ] Páginas do grupo respondem com `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex` e `Cache-Control: no-store`

**Imagens**
- [ ] Capa válida grava `Projeto.capa` e substitui a anterior; extra válida cria `ImagemProjeto`
- [ ] 7ª imagem extra, arquivo `.jpg` que não é imagem, GIF e imagem > 3 MB → recusados (400), nada gravado
- [ ] PNG renomeado para `.jpg` → aceito e gravado como `.png`
- [ ] Nome gravado = `projetos/<uuid>.<ext>`, sem o nome original
- [ ] Remover imagem de **outro** projeto → 404, nada muda
- [ ] Projeto não editável (`em_revisao`, `publicado`, prazo encerrado, votação aberta) → upload e remoção dão 403, nada gravado
- [ ] Nenhuma requisição de upload aceita mais de um arquivo

**Vitrine pública**
- [ ] Projeto `publicado` → 200 com título, resumo, descrição, equipe, links e galeria
- [ ] Slug inexistente e projeto `em_revisao`, `ajustes` ou `pre_cadastrado` → 404 idêntico
- [ ] HTML contém `og:title`, `og:description`, `og:image` (URL absoluta https), `og:url` e `twitter:card`
- [ ] Descrição com `<script>` aparece escapada, sem executar
- [ ] O HTML da vitrine e de `/como-votar/` não contém nenhum link ou formulário para `/entrar`, `/estacao`, `/votar`, `/votos` ou `/visitantes` (teste automático, G8)
- [ ] O HTML não contém `representante_nome`, RA nem token
- [ ] Projeto publicado numa edição anterior continua acessível
- [ ] Página legível em 360 px de largura, sem rolagem horizontal
- [ ] **Manual, antes de 13/10**: o link de um projeto com capa de ~3 MB, colado numa conversa do WhatsApp, mostra a prévia com a imagem (ver "Riscos")
- [ ] Testes do caminho crítico passando (`pytest`), CI verde

**Fatiamento sugerido (PRs até ~300 linhas, sem migrations e testes)**
1. `vitrine: reivindicação por RA` — serviço, rate limit, `/grupo/` (10/10)
2. `vitrine: edição pelo link` — formulário, Salvar e Enviar para revisão, equipe (10/10)
3. `vitrine: imagens do projeto` — upload uma a uma e remoção (10/10)
4. `vitrine: página pública e Open Graph` — `/projeto/<slug>/`, `/como-votar/` (12/10; depende do `base.html` do projeto)

## Riscos
- **Prévia do WhatsApp com capa grande** (apontado pelo coordenador): há
  relatos de limite de algumas centenas de KB para o `og:image`. Testar
  com uma capa de ~3 MB antes de 13/10. Se a prévia falhar, será preciso
  uma miniatura da capa — hoje fora de escopo (spec 01 não redimensiona);
  nesse caso vira proposta em `docs/02-decisoes.md` e alteração coordenada
  com a spec 01.
- **Prazo apertado**: as fatias 1 a 3 vencem em 10/10 e a 4 depende do
  `base.html` do coordenador.

## Perguntas em aberto
Dúvidas para o coordenador, **antes** de implementar:

1. **Corpo da requisição no servidor.** O desenho agora envia uma imagem
   por requisição (≤ 3 MB, com o formulário perto de 3,5 MB). Ainda assim
   o padrão do nginx (1 MB) recusaria. O critério de escolha do servidor
   (ADR-006, até 08/10) pode exigir aceitar pelo menos **4 MB** por
   requisição?
2. **Texto fixo do convite.** Qual o local e o horário exatos do evento
   para o template?
3. **`base.html` do projeto.** Caminho e blocos que as minhas páginas devem
   usar (proposta: `templates/base.html`, com os blocos `titulo`, `meta`
   e `conteudo`). Enquanto não existir, desenvolvo contra um stub local que
   não vai no PR.

### Respondidas pelo parecer do coordenador (PR #23)
- **Editar em `em_revisao`**: não. "Salvar" mantém o status; "Enviar para
  revisão" só sem pendências; em `em_revisao` a tela é somente leitura.
- **Logs**: `/grupo/editar/` entra no critério do servidor; o token fica na
  URL, sem troca por sessão.
- **Rate limit**: 50 falhas/10 min por IP; global sobe de 200 para
  1.000/h; IPv6 pelo /64.
- **Local e horário**: texto fixo no template, sem campo novo na `Edicao`.
- **Identidade visual e `base.html`**: do projeto (variáveis CSS + logo SVG
  em `static/` da raiz); o coordenador cria a estrutura.
- **`/projetos/`**: fora de 12/10.
- **Upload de ~21 MB**: mudar o desenho (imagens uma a uma — acima).
- **Chave do IP**: usar `ip_do_cliente(request)` e `chave_ip(ip)` de
  `cadastro/seguranca.py`; o cabeçalho é `DJANGO_IP_HEADER`.
- **Reivindicação depois do prazo**: recusar com a resposta genérica.

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
