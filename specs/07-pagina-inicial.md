# Spec — Página inicial e identidade visual

- **Responsável**: Guilherme (@guilhermepama), coordenador — mexe em
  `base.html`, `static/` e numa rota nova do app `vitrine` (frente do
  Cleiton, avisado no PR)
- **Status**: em implementação
- **Depende de**: ADR-002 (stack), spec 01 (models), spec 02 (vitrine
  pública, `/como-votar/`, `/grupo/`), protótipo v1 aprovado em 11/10
  (repositório `guilhermepama/vitrine-cps-prototipo`, `index.html`)

## Objetivo
Dar ao endereço raiz (`vitrinefatec.com.br/`) uma página inicial que convide a
comunidade para a Mostra e liste os projetos publicados da edição ativa, e
levar a identidade visual aprovada no protótipo v1 para o `base.css` e o
`base.html` que todas as telas herdam.

## Escopo
- **Identidade visual** no `static/css/base.css`: tokens do protótipo
  (papel `#ECE7DA`, célula `#F5F2EA`, tinta `#121316`, vermelho da marca
  `#B20000`, verde `#1E7F3E` só para confirmação), sem cantos arredondados
  nem sombras. Os tokens antigos (`--cor-fundo`, `--cor-acento`…) continuam
  existindo com os valores novos, para as telas já prontas não quebrarem.
- **Fontes servidas de `static/fonts/`** (Archivo variável, IBM Plex Sans
  400/500/600, IBM Plex Mono 400/500; subconjunto latin; licença OFL ao lado
  dos arquivos). Nada carregado do Google.
- **`templates/base.html`**: topo com a marca (logo SVG, link para `/`),
  bloco `menu` vazio por padrão e rodapé institucional. Os blocos existentes
  (`titulo`, `meta`, `conteudo`, `topo`, `rodape`, `classe_main`) não mudam.
  Blocos novos: `scripts` no fim do `body` e `rodape_edicao` na última
  linha do rodapé (vazio por padrão; a home preenche com "Edição {nome} ·
  dd.mm" quando há edição ativa). Favicon (`static/img/favicon.svg`,
  vermelho da marca) no bloco novo `icone`, que a ficha da banca zera (papel sem links).
- **Rota `/`** (`vitrine:inicio`) com as seções do protótipo: hero com a
  fachada, ficha do evento, faixa dos cursos (DSM, GTUR), 01 A Mostra, 02 Quem faz,
  03 Projetos e a chamada da Fatec com o convite ao vestibular (links para
  o site oficial da Fatec Olímpia e o portal do vestibular; datas do
  1º semestre de 2027 em texto fixo, revistas a cada edição). A Área do
  grupo continua no topo e no rodapé.
- **Filtro por curso** em JavaScript (`static/js/`), como melhoria
  progressiva: sem JavaScript, todas as turmas aparecem e o filtro fica
  escondido.
- **Menu do celular** (hambúrguer) em `static/js/menu.js`.
- **Rolagem suave** nas âncoras da página (CSS `scroll-behavior`), desligada para quem pede menos movimento no sistema (`prefers-reduced-motion`); o destino para abaixo do topo fixo.
- **Página do projeto** (`/projeto/<slug>/`) no layout do protótipo: capa em prancha, ficha técnica preta, 01 Sobre (com os links), 02 Galeria, 03 Equipe, convite vermelho e registro preto em edição passada. Menu: "Ver todos os projetos" e "Área do grupo". **Sem a seção "Impacto"** do protótipo nesta edição (não há campos no model; decisão do coordenador, 16/10 — fica para edição futura, sem ADR nova). Os links externos são rotulados pelo domínio, via filtro `dominio` em `vitrine/templatetags/vitrine_extras.py` (tira o `www.`; URL vazia ou malformada vira ""). O botão do convite diz "Como votar" (no lugar do "Quero votar" da spec 02) e continua indo só para `/como-votar/`.
- **Cédula do visitante** (`/votar`, spec 03) no visual novo, **com a regra atual** (1 toque = 1 voto): estilos saem do `<style>` do template para o `base.css`; o script continua no template (o teste da spec 03 o lê do HTML), com uma linha a mais em `marcar()` para o CSS separar "enviando" de "votado". Cada linha da cédula mostra o resumo do projeto abaixo do título, quando ele existe. O `votar.html` do protótipo (notas 1–5) entra junto com o backend novo (tarefa do Renan).
- **Estação de credenciamento** (`/estacao/<id>`, spec 03) e **página "QR expirado"** no visual novo: estilos saem do `<style>` dos templates para o `base.css`; o script da estação fica no template sem alteração (o teste o lê do HTML). A estação cabe na janela sem rolagem (notebook, TV ou tablet; QR à direita em paisagem, abaixo do título em retrato), sem link para fora. A página "QR expirado" continua com corpo constante e texto genérico (serve a todas as recusas).
- **Cadastro do visitante** (`/visitantes`, spec 03) e **tela "Entrando…"** (`/entrar`) no visual novo: estilos saem do `<style>` dos templates para o `base.css`. O cadastro usa a grade da Área do grupo (texto curto à esquerda, formulário na célula clara; no celular, o formulário logo abaixo do título), topo sem link e a mesma mensagem genérica de erro, sem marcar campo (G12); o texto do consentimento não muda. No `/entrar`, o script, o `json_script` e o `noscript` ficam sem alteração.
- **Telas da área do grupo** (`/grupo/`, link único, 429 e link inválido) no layout novo, sem mudar comportamento nem os textos que a spec 02 exige; o script do "Copiar" sai do template para `static/js/copiar-link.js`. Como essas telas são curtas, o `base.css` ganha a regra global `@media screen { body { display: flex; flex-direction: column; min-height: 100vh } body > main { flex: 1 } }`, que leva o rodapé ao fim da janela em qualquer página (só na tela; a impressão pagina sozinha).
- **Tela de edição do grupo** (`/grupo/editar/<token>/`) no layout novo, sem mudar view, forms, nomes de campos, `acao` (`salvar`/`enviar`) nem as mensagens da spec 02: cabeçalho com turma e selo da situação; no desktop, conteúdo à esquerda e painel fixo à direita com "O que falta para a publicação" e os botões Salvar / Enviar para revisão (fora do `<form>`, ligados pelo atributo `form`); no celular, o painel vem no fim. **Imagens antes do texto**: sem JavaScript, cada envio de imagem recarrega a página, então quem segue a ordem da tela manda as fotos antes de digitar (o aviso "Salve o texto antes de enviar imagens" continua no HTML). Contador de caracteres no resumo e na descrição em `static/js/contador.js` (melhoria progressiva). Galeria montada como grade: cada imagem com a legenda editável embaixo (rota `vitrine:imagem_legenda`, spec 02) e Remover, e ao lado da última um card "+ Adicionar imagem" até completar 6. Capa e card "+" enviam a imagem assim que o arquivo é escolhido, com a prévia e "Enviando…" no próprio espaço; formato ou tamanho fora do limite é recusado na hora. Com JavaScript (`static/js/imagens.js`), enviar, trocar a capa, salvar legenda e remover vão por `fetch` para as mesmas rotas e só a seção de Imagens e o painel "O que falta" são trocados pela resposta: a página não recarrega, a rolagem fica onde está e o texto digitado não se perde. Sem JavaScript, escolhe, clica no botão e a página recarrega. Sair da página com texto não salvo pede confirmação (`static/js/aviso-ao-sair.js`). Salvamento automático enquanto digita fica fora (exige rota nova: o formset da equipe duplicaria integrantes). Somente leitura mostra o que foi enviado em linhas, sem formulário.
- O 404 da página de projeto passa a ter "Conhecer a Mostra" apontando
  para `/` (antes ia para `/como-votar/` porque não havia página inicial).
- **Página `/projetos/`** (`vitrine:projetos`, decisão do coordenador, 16/10): a lista completa
  por turma e o filtro por curso saem da home e vão para cá. A home passa a mostrar **4 projetos
  sorteados a cada visita** e o botão "Ver todos os N projetos". "Ver todos os projetos" da página
  do projeto e "Projetos" do rodapé apontam para `/projetos/`.
- **Semana da Tecnologia nos textos** (decisão do coordenador, 16/10): a Mostra é um dos dias da
  Semana da Tecnologia da Fatec Olímpia (oficinas, apresentações, palestras, workshops), e o
  Vitrine divulga a Semana inteira. Nesta edição só os textos mudam: hero, 01 A Mostra, 02 Quem faz,
  descrições e rodapé. O `<title>` da home continua o mesmo.
- **Página `/semana-da-tecnologia/`** (`vitrine:semana`, decisão do coordenador, 16/10): a
  Semana da Tecnologia da Fatec Olímpia. Abertura, 01 O que acontece (oficinas e workshops,
  palestras e apresentações, Conexão Fatec com link para `/projetos/`), 02 Conexão Fatec
  (`#mostra`: texto que explica o evento ao visitante, com data e horário — a partir das 19h —, os
  quatro blocos — quando, o que, quem e você (o voto do público, sem link de voto, G8) —, os 4 projetos sorteados como na home e o botão "Ver todos os N projetos") e a chamada do vestibular
  (partial `_chamada_vestibular.html`, o mesmo da home). Texto fixo; nome e data da Mostra
  vêm da `Edicao` ativa; consultas constantes. No rodapé, "Semana da Tecnologia".
- **Menu** (home, `/projetos/` e Semana, partial `_nav_principal.html`): 01 A Mostra (seção da
  Mostra na página da Semana, `#mostra`), 02 Semana da Tecnologia, 03 Projetos (`/projetos/`) e
  Área do grupo; a página atual fica marcada. Abaixo de 1000 px, "A Mostra" e "Semana da
  Tecnologia" (`.so-desktop`) só entram no menu com JS (menu sanfona de `menu.js`); sem JS, nessa
  largura, a Semana continua alcançável pelo link do rodapé e pelo texto de "Quem faz".
- **"02 Quem faz" na home** fala só do Vitrine Fatec (o que mostra e o que DSM construiu para GTUR
  e a coordenação), com link para a página da Semana; sem os quatro blocos de
  itens. "Quem faz" (02) vem antes de "Projetos" (03).
- Citar a Etec nos textos da home e do rodapé (decisão do coordenador, 16/10). Turmas da Etec
  cadastradas continuam listadas pelos dados, depois das da Fatec.
- Portar o `votar.html` do protótipo (depende da decisão notas 1–5 × 1 toque).
- Tema escuro e escolha de tema (o protótipo deixou como proposta para a
  próxima edição). A página é sempre clara; nada segue o tema do aparelho.
- Busca, paginação e acervo de edições passadas em `/projetos/`.
- Programação da Semana da Tecnologia (lista de eventos por dia): fica para a próxima edição,
  com cadastro no admin (proposta em `docs/02-decisoes.md`).
- Campos novos em models, migrations, admin.
- Texto que dependa da regra do voto além dos critérios: a home cita os três
  critérios da avaliação do público (impacto social, impacto ambiental e
  inovação, decisão de 16/10), sem dizer como a nota é dada.

## Comportamento esperado
- **Edição exibida** = `Edicao.objects.ativa()`. Projetos de outras edições
  não aparecem na home (o link permanente de cada um continua valendo).
- **Projetos listados** (em `/projetos/`) = só `status=publicado` da edição ativa, agrupados
  por `Turma`. Ordem das turmas: Fatec antes de Etec, depois a sigla do
  curso, o período do maior para o menor e o turno; dentro da turma, por
  título.
- **Home**: até 4 cartões (`QUANTIDADE_NA_HOME`) sorteados a cada visita entre os publicados
  da edição ativa, exibidos na ordem das turmas. Sorteio e não "os primeiros" porque a ordem
  das turmas mostraria sempre a mesma turma, e a vitrine fixa favoreceria um grupo na votação.
  Com mais de 4 publicados, o texto avisa do sorteio e aparece o botão "Ver todos os N projetos"
  para `/projetos/`; com até 4, todos aparecem e não há botão. A home não tem filtro.
- **Cartão do projeto** (igual na home e em `/projetos/`): capa (recortada 1,91:1), curso e período, número
  de integrantes, título, resumo (2 linhas), quais links existem
  (repositório, demo, vídeo; "—" se nenhum). O cartão inteiro é um link
  para `/projeto/<slug>/`.
- **Título da seção 03 e de `/projetos/`**: quantidade de projetos e de turmas por extenso até
  vinte ("Oito projetos, cinco turmas"; "Um projeto, uma turma"); acima de
  vinte, em algarismos.
- **Chips do filtro** (só em `/projetos/`): "Todos" + um chip por curso que tem projeto
  publicado, na ordem das turmas, pela `Curso.sigla`. O filtro só aparece
  quando há projeto publicado em dois ou mais cursos; com um curso só, não
  há o que filtrar e o bloco nem é renderizado.
- **Datas e pesos** vêm da `Edicao`: dia e mês no bloco grande, dia da
  semana por extenso na ficha, "Edição {nome}" no hero, pesos da banca e do
  público na nota de premiação. Horário (19h) e endereço são texto fixo,
  como na spec 02.
- **Sem edição ativa**: o hero e as seções institucionais aparecem; a
  ficha do evento e a nota de premiação somem; a seção 03 diz que os
  projetos aparecem quando forem publicados.
- **Edição ativa sem projeto publicado**: a seção 03 mostra o mesmo aviso,
  sem filtro.
- **Depois do evento** (`data_evento` anterior a `timezone.localdate()`):
  a ficha troca "Dia e horário" por "Realizada em", sem horário; o resto
  não muda até a coordenação ativar a próxima edição.
- Nenhum dado pessoal além do que a página pública do projeto já mostra
  (a home só conta integrantes, não lista nomes).

## Dados
Esta spec não cria tabelas nem migrations. Lê `Edicao` (ativa,
`nome`, `data_evento`, `peso_banca`, `peso_publico`), `Curso`, `Turma`,
`Projeto` (publicados) e a contagem de `Integrante`. Não escreve nada.

## Endpoints / telas
| Nome | Método | Rota | Entrada | Saída | Erros |
|---|---|---|---|---|---|
| `vitrine:inicio` | GET | `/` | — | HTML da página inicial | — |
| `vitrine:projetos` | GET | `/projetos/` | — | HTML com todos os projetos publicados da edição ativa | — |
| `vitrine:semana` | GET | `/semana-da-tecnologia/` | — | HTML da Semana da Tecnologia | — |

Rota em `vitrine/urls.py`; o include raiz em `""` já existe.

## Guardrails aplicáveis
8 (nenhum caminho de voto: a home só leva a `/projeto/…`, `/projetos/`, `/grupo/`,
`/como-votar/` e a âncoras da própria página; `/projetos/` só a `/`, `/projeto/…` e `/grupo/`), 11 (por analogia: nada de
RA, token ou representante na página), 13 (só ORM), 17.

## Critérios de aceite
- [ ] `GET /` responde 200 com `<title>` "Vitrine Fatec — Projetos e eventos da Fatec Olímpia"
- [ ] Lista só projetos `publicado` da edição ativa; `pre_cadastrado`, `em_revisao`, `ajustes` e projetos de outra edição não aparecem
- [ ] Turmas na ordem da spec em `/projetos/`; contagem por extenso no título da seção 03 e de `/projetos/`
- [ ] Home com no máximo 4 cartões sorteados; botão para `/projetos/` só com mais de 4 publicados; sem filtro na home
- [ ] `GET /projetos/` responde 200 com `<title>` "Projetos — Vitrine Fatec", lista todos os publicados da edição ativa e tem o filtro por curso
- [ ] Sem edição ativa e sem projeto publicado → 200 com o aviso, sem filtro
- [ ] Data, dia da semana, nome da edição e pesos vêm da `Edicao`; depois do evento, "Realizada em"
- [ ] `GET /semana-da-tecnologia/` responde 200 com `<title>` "Semana da Tecnologia — Vitrine Fatec", lista as atividades, data da Mostra vinda da `Edicao`, termina com o convite ao vestibular, 4 projetos sorteados e consultas constantes
- [ ] Nenhum `href`, `action` ou `src` da home, de `/projetos/` nem de `/semana-da-tecnologia/` aponta para `/entrar`, `/estacao`, `/votar`, `/votos` ou `/visitantes` (G8)
- [ ] `representante_nome` e nomes de integrantes não aparecem na home nem em `/projetos/`
- [ ] Número de queries constante na home e em `/projetos/` (não cresce com o número de projetos)
- [ ] `base.css` sem largura fixa acima de 360 px (teste existente); topo e rodapé fora da impressão (teste existente)
- [ ] Fontes servidas de `static/fonts/`; nenhuma URL do Google no HTML ou no CSS
- [ ] A ficha da banca continua sem nenhum link além do CSS
- [ ] O 404 do projeto leva a `/`
- [ ] Testes do caminho crítico passando

## Perguntas em aberto
Nenhuma bloqueante. Pendências herdadas do protótipo, a decidir fora deste PR:
- Fonte e direito de uso da foto da fachada antes de produção.
- Sigla e cursos da Etec (a home usa o que estiver cadastrado).
- Nome: o logo diz "Vitrine Fatec Olímpia"; textos usam "Vitrine Fatec".
