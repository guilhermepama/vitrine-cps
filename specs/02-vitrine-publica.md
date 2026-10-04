# Spec — Vitrine pública e área do grupo

- **Responsável**: Cleiton (@gustimmolp)
- **Status**: pronta para implementar (parecer e respostas do coordenador
  incorporados; aguardando a aprovação final no PR #23)
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
  Campos: resumo, descrição, componente de origem, links e equipe
  (integrantes). O **título não é editável** pelo grupo: vem da lista das
  coordenações (ver "Wireframes e decisões").
- **Imagens enviadas uma a uma**, em requisições próprias: capa e até 6
  imagens extras, com legenda opcional, e remoção individual. Trocar a
  capa ou remover uma extra **apaga o arquivo antigo do storage** depois
  de confirmada a gravação.
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
- Convite para o evento, com a data vinda da `Edicao` e o **texto fixo no
  template** (nesta edição, sem campo novo): "às **19h**, no campus da
  **Fatec Olímpia** — Av. Governador Adhemar Pereira de Barros, km 3,
  Recanto Bela Vista, Olímpia/SP". Um botão leva a uma página de explicação
  do voto presencial, `/como-votar/` (guardrail 8), com o nome de rota
  `vitrine:como_votar` — a spec 03 redireciona por esse nome.
- Templates das páginas desta spec, herdando o **`templates/base.html` do
  projeto** (blocos `titulo`, `meta` e `conteudo`; criado pelo coordenador,
  com as variáveis de CSS e o logo SVG em `static/` do projeto),
  mobile-first.
- **Avatar do projeto = monograma gerado no template** (sigla do curso ou
  inicial do título): o model não tem campo de logo, e esta spec não cria.
- O topo mostra o **nome da edição** do projeto (`Edicao.nome` da turma),
  não um texto fixo: o link é permanente e os projetos antigos mantêm a
  edição deles.
- O **corpo do projeto** (capa, resumo, links, descrição, galeria, equipe)
  fica num partial `vitrine/_corpo_projeto.html`, sem nenhum link de voto,
  que a página pública inclui. Outro app pode incluí-lo (ex.: a tela de voto
  da spec 03, se ela mudar), mas a página pública continua sem caminho de
  voto (G8).
- A **capa** aparece recortada em banner (`object-fit: cover`) na página;
  o `og:image` usa a imagem original. No upload, a tela orienta a proporção
  ideal (~1,91:1, por exemplo 1200×630 px) para a prévia do WhatsApp.

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
- Edição do `slug`, do `titulo` ou do `representante_nome` pelo grupo.
- Campo novo "o que cada integrante fez" (previsto no wireframe): exige
  mudança no model `Integrante` da spec 01, que hoje só tem nome, papel e
  ordem. O campo `papel` ("Função", ex.: Front-end) cobre o essencial nesta
  edição; vira proposta para a próxima.
- Redesenhar os wireframes: as diferenças em relação a eles estão em
  "Wireframes e decisões".
- Retirar o projeto de `em_revisao` pelo próprio grupo: quem precisa
  corrigir fala com a coordenação, que devolve para ajustes.

## Comportamento esperado

### Reivindicar o projeto (`/grupo/`)
- Quando o representante abre `/grupo/`, o sistema exibe o formulário (campo
  RA e a explicação de que o link aparece **uma vez** e deve ser guardado).
- Quando envia o RA, o sistema: (1) valida o formato com
  `cadastro.seguranca.hash_ra`, que recusa (`ValueError`) o que não tiver
  5 a 20 dígitos depois de remover espaço, ponto, hífen e barra — formato
  inválido recebe a **mesma resposta genérica** abaixo, conta como falha
  no rate limit e **não consulta o banco**; (2) checa o
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
  resposta leva `Cache-Control: no-store`. A página tem o botão "Copiar"
  (JavaScript mínimo e opcional: sem JS o link continua selecionável) e o
  botão "Abrir edição do projeto".
- Quando dois requests tentam reivindicar o mesmo projeto ao mesmo tempo,
  só um recebe o link; o outro recebe a resposta genérica.
- Quando o RA é malformado, não existe, já foi reivindicado, é de outra
  edição, o projeto não está `pre_cadastrado` **ou o prazo de edição já
  acabou (ou a votação já abriu)**, o sistema responde **a mesma página,
  com o mesmo status (400) e o mesmo texto**: "Não foi possível acessar com
  esse RA. Confira os números e tente de novo. Se o RA estiver certo, o link
  de edição do grupo pode já ter sido retirado — use o link que foi
  guardado ou procure a coordenação." Nunca diz qual regra barrou. O
  campo do RA volta **vazio** (a página de erro não repete o que foi
  digitado).
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
- **Texto não salvo × imagens.** O envio de imagem é outra requisição e
  recarrega a página: o que foi digitado e não foi salvo se perde. Para não
  haver surpresa, a página mostra, **junto dos campos de imagem**, o aviso
  visível "Salve o texto antes de enviar imagens: o envio recarrega a
  página e o que não foi salvo se perde." (Não há rascunho automático nem
  JavaScript para isso nesta edição.)
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
- Cada upload ou remoção roda numa transação que **trava a linha do
  `Projeto`** (`select_for_update`) **antes** de contar as extras. Assim,
  dois uploads simultâneos com 5 extras gravam só um (o limite de 6 vale
  mesmo sob concorrência).
- `tipo=capa` grava (ou substitui) `Projeto.capa`. `tipo=extra` cria uma
  `ImagemProjeto`; a 7ª extra é recusada.
- `POST .../imagem/<id>/remover/` remove uma imagem extra **do próprio
  projeto**; `<id>` de outro projeto responde 404.
- **Arquivo antigo apagado do bucket.** Ao trocar a capa ou remover uma
  extra, o arquivo anterior é apagado do storage por
  `transaction.on_commit` — só **depois** de a gravação ser confirmada. Se a
  transação falhar e for desfeita, o arquivo antigo permanece (o projeto
  ainda aponta para ele). Falha ao apagar no storage não desfaz a gravação:
  é registrada em log, sem token nem RA, e a resposta segue normal. O
  motivo: o bucket é público (domínio próprio, ADR-006), então um arquivo
  que ficasse órfão — por exemplo, a foto de aluno menor da Etec recusada
  na moderação — continuaria acessível por quem tivesse a URL.
- Tipo real, 3 MB e nome gerado pelo servidor vêm de `cadastro.imagens`
  (`validar_imagem`, G14); o limite de 6 vem de
  `ImagemProjeto.MAXIMO_POR_PROJETO` e o de 10 integrantes de
  `Integrante.MAXIMO_POR_PROJETO`. O arquivo original nunca é usado como
  nome. Imagem inválida ou grande demais → 400, nada gravado.
- As mesmas regras de "editável" valem: fora dela, 403 e nada é gravado.
- O servidor aceita corpo de **pelo menos 4 MB por requisição** (critério
  eliminatório da escolha do servidor, ADR-006): uma imagem de até 3 MB mais
  o formulário. Confirmado no ambiente publicado (ver "Dependências do
  coordenador").

### Página pública (`/projeto/<slug>/`)
- Quando o `slug` não existe **ou** o projeto não está `publicado`, o sistema
  responde o mesmo 404 (não revela projetos em revisão). A página 404
  tem o botão "Conhecer a Mostra", que leva a `/como-votar/` (não existe
  página inicial nesta edição).
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
  `<title>`: "Título — Vitrine CPS". Os links absolutos usam
  `settings.URL_PUBLICA` (`DJANGO_URL_PUBLICA`), não o `Host` da requisição.
- Bloco de convite: "Conheça este projeto no evento — [data da `Edicao`]
  às 19h, no campus da Fatec Olímpia — [endereço]" e botão "Quero votar"
  que aponta **só** para `/como-votar/` (`vitrine:como_votar`).
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
- `Projeto`: `resumo`, `descricao`, `componente_origem`, `capa`,
  `link_repositorio`, `link_demo`, `link_video`, `status` (só
  `pre_cadastrado`/`ajustes` → `em_revisao`, e só em "Enviar para
  revisão"), `reivindicado_em`, `token_edicao_hash`,
  `token_edicao_gerado_em`.
- `Integrante` e `ImagemProjeto`: criar, alterar, remover e reordenar os do
  próprio projeto.

Nunca escreve: `titulo`, `slug`, `ra_hmac`, `representante_nome`, `publicado_em`,
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
| Nome | Método | Rota | Entrada | Saída | Erros |
|---|---|---|---|---|---|
| `vitrine:projeto` | GET | `/projeto/<slug>/` | — | HTML da vitrine + Open Graph | 404 (inexistente ou não publicado) |
| `vitrine:como_votar` | GET | `/como-votar/` | — | HTML estático | — |
| `vitrine:grupo` | GET | `/grupo/` | — | formulário de RA | — |
| `vitrine:grupo` | POST | `/grupo/` | `ra` | link de edição (1 vez) | 400 resposta genérica (inclusive RA malformado); 429 rate limit |
| `vitrine:editar` | GET | `/grupo/editar/<token>/` | — | formulário, ou leitura se não editável | 404 token inválido |
| `vitrine:editar` | POST | `/grupo/editar/<token>/` | campos + integrantes + `acao` (`salvar` ou `enviar`) | confirmação | 400 validação ou pendências; 403 não editável; 404 token inválido |
| `vitrine:imagem` | POST | `/grupo/editar/<token>/imagem/` | `arquivo` (1), `tipo`, `legenda?` (multipart) | página de edição atualizada | 400 imagem inválida ou 7ª extra; 403 não editável; 404 token inválido |
| `vitrine:imagem_remover` | POST | `/grupo/editar/<token>/imagem/<id>/remover/` | — | página de edição atualizada | 403 não editável; 404 token ou imagem inválidos |

Rotas em `vitrine/urls.py` (`app_name = "vitrine"`); o include raiz já
existe. CSRF ligado nos POSTs. Templates em `vitrine/templates/vitrine/`,
herdando o `templates/base.html` do projeto.

## Guardrails aplicáveis
3 (por analogia: nenhum segredo no código ou na resposta), 5 (por analogia:
resposta genérica na reivindicação, sem revelar qual regra barrou), 7 (por
analogia: rate limit na reivindicação), 8, 11 (por analogia: RA, token e IP
nunca em log, resposta de erro ou página pública), 12, 13, 14, 17.

Reler antes de implementar: 5 (resposta genérica), 8 (nenhum caminho de voto
na vitrine), 12 (validar toda entrada, erro genérico), 13 (só ORM) e 14
(upload).

## Critérios de aceite

**Reivindicação**
- [ ] RA válido de projeto `pre_cadastrado` da edição ativa → mostra o link e grava `reivindicado_em`, hash do token e `token_edicao_gerado_em`; o token em claro não está no banco
- [ ] RA malformado, RA inexistente, RA já reivindicado, RA de outra edição e RA depois do prazo de edição (ou com a votação aberta) → respostas **idênticas** (status 400 e corpo); o campo do RA volta vazio, sem repetir o digitado
- [ ] Recarregar o POST após o sucesso → resposta genérica, não um segundo link
- [ ] 2 POSTs simultâneos com o mesmo RA → um link emitido, um genérico
- [ ] 50 falhas do mesmo IP em 10 min passam; a 51ª → 429; sucesso não conta
- [ ] 1.000 falhas somadas de IPs diferentes em 1 hora passam; a 1.001ª → 429 para qualquer IP
- [ ] Dois endereços IPv6 do mesmo /64 contam como o mesmo IP
- [ ] RA vazio, com letra ou fora de 5–20 dígitos → resposta genérica idêntica, conta como falha no rate limit e **não consulta** o banco; `123.456-7` e `1234567` reivindicam o mesmo projeto
- [ ] A página do link mostra o link completo uma vez, o botão "Copiar" e o botão "Abrir edição do projeto"
- [ ] A chave do IP no cache vem de `chave_ip(ip_do_cliente(request))`, expira em 10 min e não contém o IP em claro; o IP não aparece em log nem em tabela de model; o app `vitrine` não lê `REMOTE_ADDR` nem `X-Forwarded-For` (revisão de código)
- [ ] O RA em claro não aparece no log, na resposta de erro nem no banco (teste captura log e resposta)
- [ ] Resposta do link tem `Cache-Control: no-store`

**Edição**
- [ ] Token inexistente, revogado e regerado → mesmo 404; o link antigo para de valer após "regerar"
- [ ] "Salvar" em `pre_cadastrado` ou `ajustes` grava os dados e **mantém o status**, mesmo incompleto
- [ ] O formulário do grupo não mostra o título como campo editável; um POST com campo `titulo` não altera `titulo` nem `slug`
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
- [ ] A página de edição mostra, junto dos campos de imagem, o aviso "Salve o texto antes de enviar imagens" (teste de conteúdo)

**Imagens**
- [ ] Capa válida grava `Projeto.capa` e substitui a anterior; extra válida cria `ImagemProjeto`
- [ ] Trocar a capa → o arquivo antigo **não existe mais no storage** depois do commit; remover uma extra → idem
- [ ] Se a transação do upload falhar e for desfeita, o arquivo antigo **continua** no storage e no projeto
- [ ] Falha do storage ao apagar o arquivo antigo não desfaz a gravação nem derruba a resposta, e fica registrada em log sem token nem RA
- [ ] Com 5 extras, 2 uploads **simultâneos** → só um grava; o projeto termina com 6 extras (teste de concorrência)
- [ ] 7ª imagem extra, arquivo `.jpg` que não é imagem, GIF e imagem > 3 MB → recusados (400), nada gravado
- [ ] PNG renomeado para `.jpg` → aceito e gravado como `.png`
- [ ] Nome gravado = `projetos/<uuid>.<ext>`, sem o nome original
- [ ] Remover imagem de **outro** projeto → 404, nada muda
- [ ] Projeto não editável (`em_revisao`, `publicado`, prazo encerrado, votação aberta) → upload e remoção dão 403, nada gravado
- [ ] Nenhuma requisição de upload aceita mais de um arquivo

**Vitrine pública**
- [ ] Projeto `publicado` → 200 com título, resumo, descrição, equipe, links e galeria
- [ ] Slug inexistente e projeto `em_revisao`, `ajustes` ou `pre_cadastrado` → 404 idêntico
- [ ] HTML contém `og:title`, `og:description`, `og:image` (URL absoluta https), `og:url` e `twitter:card`; os links absolutos usam `settings.URL_PUBLICA`, não o `Host` da requisição
- [ ] `reverse("vitrine:como_votar")` resolve para `/como-votar/` e a página responde 200
- [ ] O topo mostra `Edicao.nome` da edição do projeto; um projeto de edição antiga mostra o nome da edição dele
- [ ] O avatar é um monograma gerado (sigla do curso ou inicial do título), sem campo novo no model
- [ ] A página 404 tem o botão "Conhecer a Mostra" apontando para `/como-votar/`
- [ ] O partial `vitrine/_corpo_projeto.html` não contém link nem formulário de voto (o teste de G8 também o cobre)
- [ ] A capa aparece recortada na página, e o `og:image` aponta para o arquivo original; a tela de upload mostra a proporção ideal (~1,91:1)
- [ ] O convite mostra a data da `Edicao`, "19h" e o endereço do campus da Fatec Olímpia
- [ ] Descrição com `<script>` aparece escapada, sem executar
- [ ] O HTML da vitrine e de `/como-votar/` não contém nenhum link ou formulário para `/entrar`, `/estacao`, `/votar`, `/votos` ou `/visitantes` (teste automático, G8)
- [ ] O HTML não contém `representante_nome`, RA nem token
- [ ] Projeto publicado numa edição anterior continua acessível
- [ ] Página legível em 360 px de largura, sem rolagem horizontal
- [ ] **Manual, antes de 13/10**: o link de um projeto com capa de ~3 MB, colado numa conversa do WhatsApp, mostra a prévia com a imagem (ver "Riscos")
- [ ] **Manual, no ambiente publicado (deploy, até 08/10)**: o upload de uma imagem de 3 MB funciona (o servidor aceita pelo menos 4 MB por requisição)
- [ ] Testes do caminho crítico passando (`pytest`), CI verde

**Fatiamento sugerido (PRs até ~300 linhas, sem migrations e testes)**
1. `vitrine: reivindicação por RA` — serviço, rate limit, `/grupo/` (10/10)
2. `vitrine: edição pelo link` — formulário, Salvar e Enviar para revisão, equipe (10/10)
3. `vitrine: imagens do projeto` — upload uma a uma e remoção (10/10)
4. `vitrine: página pública e Open Graph` — `/projeto/<slug>/`, `/como-votar/`, partial do corpo do projeto e monograma (12/10; depende do `base.html` do projeto)

## Wireframes e decisões
Referência: wireframes do projeto (artefato "Wireframe — Página de Projeto
(Vitrine CPS)", https://claude.ai/artifact/QGake9QNCwsKcF5TbsgxYg). Telas
desta spec: página do projeto (desktop e celular), 404, reivindicação pelo
RA, RA recusado, link único de edição e edição do projeto. As telas da
estação, do visitante, da cédula e do admin são das specs 01, 03, 04 e 06.

Onde o wireframe e esta spec divergem, vale a spec. Os wireframes devem ser
atualizados para refletir o abaixo.

| Wireframe | Decisão desta spec | Situação |
|---|---|---|
| Botão único "Salvar e enviar para revisão" | Dois botões: "Salvar" (mantém o status) e "Enviar para revisão" (só sem pendências), conforme o parecer do coordenador | Aplicado |
| Título "travado (pedido)", com a nota de decidir e registrar | O grupo **não edita o título**; ele vem da lista das coordenações. O slug nunca muda | Aplicado como proposta — confirmar (pergunta 2) |
| Campo novo "o que o integrante fez" | Fora de escopo: exigiria mudar `Integrante` (spec 01). O campo `papel` ("Função") cobre | Adiado |
| Capa e galeria com "+ Adicionar imagem" e um único salvar | Cada imagem é um envio próprio; aviso "salve o texto antes de enviar imagens" | Aplicado |
| Tela de RA recusado repete o RA digitado | Não repete: o campo volta vazio (G11 por analogia) | Aplicado |
| Mensagem de RA recusado, com a dica do "link retirado" | Adotada, para todos os casos de falha (inclusive RA malformado), com a mesma resposta 400 | Aplicado |
| Link `/grupo/<token>` | Mantida a rota `/grupo/editar/<token>/` (a ADR-006 já a cita no critério de logs) | Aplicado |
| Capa em ~3,7:1 | Banner recortado na página; `og:image` com a imagem original; orientação ~1,91:1 no upload | Aplicado |
| Botão "Conhecer a Mostra" do 404 sem destino | Leva a `/como-votar/` | Aplicado |
| "Mostra 2026/2" fixo no topo | `Edicao.nome` da edição do projeto | Aplicado |
| "local · horário · como chegar" | Texto fixo definido pelo coordenador (19h, campus da Fatec Olímpia, endereço) | Aplicado |
| Tela "Projeto em modo votação" reaproveita o corpo da página | Partial `vitrine/_corpo_projeto.html` reaproveitável, sem link de voto na página pública | Aplicado — combinar com o Renan (pergunta 3) |
| Voto do público em notas de 1 a 5 por critério | Fora desta spec: muda as specs 03 e 04 e o cálculo 70/30; decisão do coordenador e do Renan. Só afeta aqui o partial acima | Não é desta spec |

**Telas que faltam no wireframe para esta spec** (a desenhar):
somente leitura (`em_revisao`, `publicado`, prazo encerrado, votação aberta),
lista "o que falta" com o botão "Enviar para revisão" desabilitado, erro de
formulário, imagem recusada e 7ª extra, aviso "salve o texto antes de enviar
imagens", 429 (muitas tentativas), 403 (edição encerrada) e link de edição
inválido (404).

## Riscos
- **Prévia do WhatsApp com capa grande** (apontado pelo coordenador): há
  relatos de limite de algumas centenas de KB para o `og:image`. Testar
  com uma capa de ~3 MB antes de 13/10. Se a prévia falhar, será preciso
  uma miniatura da capa — hoje fora de escopo (spec 01 não redimensiona);
  nesse caso vira proposta em `docs/02-decisoes.md` e alteração coordenada
  com a spec 01.
- **Prazo apertado**: as fatias 1 a 3 vencem em 10/10 e a 4 depende do
  `templates/base.html` do coordenador.
- **`base.html` e o CI das fatias 1 a 3**: os testes dessas fatias
  renderizam templates que herdam `base.html`. Sem o arquivo na `main`, o
  CI falharia (`TemplateDoesNotExist`). Ver pergunta 1.

## Dependências do coordenador (com data)
- **Até 08/10 — servidor aceita pelo menos 4 MB por requisição.** Já é
  critério eliminatório na ADR-006 (o Traefik do Coolify não limita o corpo
  por padrão); confirmar no deploy com um upload de imagem de 3 MB.
- **Antes do PR 4 (12/10) — `templates/base.html`** com os blocos `titulo`,
  `meta` e `conteudo`, as variáveis CSS e o logo SVG em `static/` do
  projeto. Até lá, as fatias 1 a 3 usam um stub local **fora dos PRs**.

## Perguntas em aberto
1. **`base.html` antes do PR 1.** Como os testes das fatias 1 a 3 (10/10)
   renderizam as páginas, o `templates/base.html` precisa existir na `main`
   antes delas, mesmo que mínimo. O coordenador pode colocar uma versão
   mínima (só os três blocos) na `main` até 07/10, e a identidade visual
   entra depois, sem mudar o nome nem os blocos? Se preferir, o PR 1 leva
   esse arquivo mínimo e o coordenador o substitui depois.

2. **Título travado para o grupo.** O wireframe traz o título travado, com a
   nota de que foi um pedido do coordenador e de que a spec permitia editar.
   Apliquei como proposta: o grupo não edita o título (vem da lista das
   coordenações; o slug nunca muda). Confirma? Se a decisão for deixar o
   grupo editar, volta o campo `titulo` ao formulário e o critério de aceite
   original.
3. **Partial do corpo do projeto.** Se a spec 03 mudar a tela de voto (notas
   por critério), o Renan pode incluir `vitrine/_corpo_projeto.html` em vez
   de duplicar a galeria e a equipe. O Renan e o coordenador concordam com
   esse reaproveitamento?

### Respondidas pelo coordenador (PR #23)
- **Editar em `em_revisao`**: não. "Salvar" mantém o status; "Enviar para
  revisão" só sem pendências; em `em_revisao` a tela é somente leitura.
- **Logs**: `/grupo/editar/` entra no critério do servidor; o token fica na
  URL, sem troca por sessão. A ADR-006 já registra: sem log de acesso no
  gunicorn nem no Traefik.
- **Rate limit**: 50 falhas/10 min por IP; global sobe de 200 para
  1.000/h; IPv6 pelo /64. O IP real vem de `X-Real-Ip`
  (`DJANGO_IP_HEADER`, ADR-006).
- **Local e horário**: texto fixo no template, sem campo novo na `Edicao`:
  "às 19h, no campus da Fatec Olímpia — Av. Governador Adhemar Pereira de
  Barros, km 3, Recanto Bela Vista, Olímpia/SP".
- **Identidade visual e `base.html`**: do projeto (`templates/base.html`,
  blocos `titulo`, `meta` e `conteudo`; variáveis CSS + logo SVG em
  `static/` da raiz); o coordenador cria a estrutura.
- **`/projetos/`**: fora de 12/10; fatia pequena depois de 13/10, se houver
  folga.
- **Upload de ~21 MB**: mudar o desenho (imagens uma a uma) e exigir 4 MB
  por requisição no servidor.
- **Chave do IP**: usar `ip_do_cliente(request)` e `chave_ip(ip)` de
  `cadastro/seguranca.py`; o cabeçalho é `DJANGO_IP_HEADER`.
- **Reivindicação depois do prazo**: recusar com a resposta genérica.
- **Nome da rota**: `/como-votar/` com `name="como_votar"`
  (`vitrine:como_votar`), porque a spec 03 redireciona por esse nome.
- **Arquivo antigo no bucket**: apagar com `transaction.on_commit` ao
  trocar a capa ou remover uma extra (nada de "órfão aceito").
- **Texto não salvo × upload**: aviso visível junto dos campos de imagem.
- **Limite de 6 extras sob concorrência**: travar a linha do `Projeto`
  antes de contar.

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
