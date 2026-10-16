# Spec — Página inicial e identidade visual

- **Responsável**: Guilherme (@guilhermepama), coordenador — mexe em
  `base.html`, `static/` e numa rota nova do app `vitrine` (frente do
  Cleiton, avisado no PR)
- **Status**: em implementação
- **Depende de**: ADR-002 (stack), spec 01 (models), spec 02 (vitrine
  pública, `/como-votar/`, `/grupo/`), protótipo v1 aprovado em 11/10
  (repositório `guilhermepama/vitrine-cps-prototipo`, `index.html`)

## Objetivo
Dar ao endereço raiz (`vitrinecps.com.br/`) uma página inicial que convide a
comunidade para a Mostra e liste os projetos publicados da edição ativa, e
levar a identidade visual aprovada no protótipo v1 para o `base.css` e o
`base.html` que todas as telas herdam.

## Escopo
- **Identidade visual** no `static/css/base.css`: tokens do protótipo
  (papel `#ECE7DA`, célula `#F5F2EA`, tinta `#121316`, vermelho CPS
  `#B20000`, verde `#1E7F3E` só para confirmação), sem cantos arredondados
  nem sombras. Os tokens antigos (`--cor-fundo`, `--cor-acento`…) continuam
  existindo com os valores novos, para as telas já prontas não quebrarem.
- **Fontes servidas de `static/fonts/`** (Archivo variável, IBM Plex Sans
  400/500/600, IBM Plex Mono 400/500; subconjunto latin; licença OFL ao lado
  dos arquivos). Nada carregado do Google.
- **`templates/base.html`**: topo com a marca (logo SVG, link para `/`),
  bloco `menu` vazio por padrão e rodapé institucional. Os blocos existentes
  (`titulo`, `meta`, `conteudo`, `topo`, `rodape`, `classe_main`) não mudam.
  Bloco novo `scripts` no fim do `body`.
- **Rota `/`** (`vitrine:inicio`) com as seções do protótipo: hero com a
  fachada, ficha do evento, faixa dos cursos (DSM, GTUR), 01 A Mostra, 02 Projetos,
  03 Quem faz e a chamada da Fatec com o convite ao vestibular (links para
  o site oficial da Fatec Olímpia e o portal do vestibular; datas do
  1º semestre de 2027 em texto fixo, revistas a cada edição). A Área do
  grupo continua no topo e no rodapé.
- **Filtro por curso** em JavaScript (`static/js/`), como melhoria
  progressiva: sem JavaScript, todas as turmas aparecem e o filtro fica
  escondido.
- **Menu do celular** (hambúrguer) em `static/js/menu.js`.
- **Rolagem suave** nas âncoras da página (CSS `scroll-behavior`), desligada para quem pede menos movimento no sistema (`prefers-reduced-motion`); o destino para abaixo do topo fixo.
- **Página do projeto** (`/projeto/<slug>/`) no layout do protótipo: capa em prancha, ficha técnica preta, 01 Sobre (com os links), 02 Galeria, 03 Equipe, convite vermelho e registro preto em edição passada. Menu: "Ver todos os projetos" e "Área do grupo". **Sem a seção "Impacto"** do protótipo nesta edição (não há campos no model; decisão do coordenador, 16/10). O botão do convite diz "Como votar" (no lugar do "Quero votar" da spec 02) e continua indo só para `/como-votar/`.
- **Cédula do visitante** (`/votar`, spec 03) no visual novo, **com a regra atual** (1 toque = 1 voto): estilos saem do `<style>` do template para o `base.css`; o script continua no template (o teste da spec 03 o lê do HTML), com uma linha a mais em `marcar()` para o CSS separar "enviando" de "votado". O `votar.html` do protótipo (notas 1–5) entra junto com o backend novo (tarefa do Renan).
- **Telas da área do grupo** (`/grupo/`, link único, 429 e link inválido) no layout novo, sem mudar comportamento nem os textos que a spec 02 exige; o script do "Copiar" sai do template para `static/js/copiar-link.js`.
- **Tela de edição do grupo** (`/grupo/editar/<token>/`) no layout novo, sem mudar view, forms, nomes de campos, `acao` (`salvar`/`enviar`) nem as mensagens da spec 02: cabeçalho com turma e selo da situação; no desktop, conteúdo à esquerda e painel fixo à direita com "O que falta para a publicação" e os botões Salvar / Enviar para revisão (fora do `<form>`, ligados pelo atributo `form`); no celular, o painel vem no fim. **Imagens antes do texto**: cada envio de imagem recarrega a página, então quem segue a ordem da tela manda as fotos antes de digitar (o aviso "Salve o texto antes de enviar imagens" continua). Contador de caracteres no resumo e na descrição em `static/js/contador.js` (melhoria progressiva). Galeria montada como grade: cada imagem com a legenda editável embaixo (rota `vitrine:imagem_legenda`, spec 02) e Remover, e ao lado da última um card "+ Adicionar imagem" até completar 6. Capa e card "+" enviam a imagem assim que o arquivo é escolhido, com a prévia e "Enviando…" no próprio espaço; formato ou tamanho fora do limite é recusado na hora (`static/js/previa-imagem.js`). Sem JavaScript, escolhe e clica no botão. Antes de enviar ou remover imagem, o texto mexido é salvo com o mesmo "Salvar" do botão (`acao=salvar`); com erro no texto, a imagem não vai e a tela avisa; sair da página com texto não salvo pede confirmação (`static/js/salvar-antes.js`). Salvamento automático enquanto digita fica fora (exige rota nova: o formset da equipe duplicaria integrantes). Somente leitura mostra o que foi enviado em linhas, sem formulário.
- O 404 da página de projeto passa a ter "Conhecer a Mostra" apontando
  para `/` (antes ia para `/como-votar/` porque não havia página inicial).

## Fora de escopo
- Citar a Etec nos textos da home e do rodapé (decisão do coordenador, 16/10). Turmas da Etec
  cadastradas continuam listadas pelos dados, depois das da Fatec.
- Portar o `votar.html` do protótipo (depende da decisão notas 1–5 × 1 toque).
- Tema escuro e escolha de tema (o protótipo deixou como proposta para a
  próxima edição). A página é sempre clara; nada segue o tema do aparelho.
- Página-índice `/projetos/`, busca, paginação, acervo de edições passadas.
- Campos novos em models, migrations, admin.
- Texto que dependa da decisão pendente sobre o voto em notas 1–5: a home
  fala em "avaliar pelo celular, uma vez por projeto", que vale para os
  dois desenhos.

## Comportamento esperado
- **Edição exibida** = `Edicao.objects.ativa()`. Projetos de outras edições
  não aparecem na home (o link permanente de cada um continua valendo).
- **Projetos listados** = só `status=publicado` da edição ativa, agrupados
  por `Turma`. Ordem das turmas: Fatec antes de Etec, depois a sigla do
  curso, o período do maior para o menor e o turno; dentro da turma, por
  título.
- **Cartão do projeto**: capa (recortada 1,91:1), curso e período, número
  de integrantes, título, resumo (2 linhas), quais links existem
  (repositório, demo, vídeo; "—" se nenhum). O cartão inteiro é um link
  para `/projeto/<slug>/`.
- **Título da seção 02**: quantidade de projetos e de turmas por extenso até
  vinte ("Oito projetos, cinco turmas"; "Um projeto, uma turma"); acima de
  vinte, em algarismos.
- **Chips do filtro**: "Todos" + um chip por curso que tem projeto
  publicado, na ordem das turmas, pela `Curso.sigla`.
- **Datas e pesos** vêm da `Edicao`: dia e mês no bloco grande, dia da
  semana por extenso na ficha, "Edição {nome}" no hero, pesos da banca e do
  público na nota de premiação. Horário (19h) e endereço são texto fixo,
  como na spec 02.
- **Sem edição ativa**: o hero e as seções institucionais aparecem; a
  ficha do evento e a nota de premiação somem; a seção 02 diz que os
  projetos aparecem quando forem publicados.
- **Edição ativa sem projeto publicado**: a seção 02 mostra o mesmo aviso,
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

Rota em `vitrine/urls.py`; o include raiz em `""` já existe.

## Guardrails aplicáveis
8 (nenhum caminho de voto: a home só leva a `/projeto/…`, `/grupo/`,
`/como-votar/` e a âncoras da própria página), 11 (por analogia: nada de
RA, token ou representante na página), 13 (só ORM), 17.

## Critérios de aceite
- [ ] `GET /` responde 200 com `<title>` "Vitrine CPS — Mostra de Projetos Fatec Olímpia"
- [ ] Lista só projetos `publicado` da edição ativa; `pre_cadastrado`, `em_revisao`, `ajustes` e projetos de outra edição não aparecem
- [ ] Turmas na ordem da spec; contagem por extenso no título da seção 02
- [ ] Sem edição ativa e sem projeto publicado → 200 com o aviso, sem filtro
- [ ] Data, dia da semana, nome da edição e pesos vêm da `Edicao`; depois do evento, "Realizada em"
- [ ] Nenhum `href`, `action` ou `src` da home aponta para `/entrar`, `/estacao`, `/votar`, `/votos` ou `/visitantes` (G8)
- [ ] `representante_nome` e nomes de integrantes não aparecem na home
- [ ] Número de queries constante (não cresce com o número de projetos)
- [ ] `base.css` sem largura fixa acima de 360 px (teste existente); topo e rodapé fora da impressão (teste existente)
- [ ] Fontes servidas de `static/fonts/`; nenhuma URL do Google no HTML ou no CSS
- [ ] A ficha da banca continua sem nenhum link além do CSS
- [ ] O 404 do projeto leva a `/`
- [ ] Testes do caminho crítico passando

## Perguntas em aberto
Nenhuma bloqueante. Pendências herdadas do protótipo, a decidir fora deste PR:
- Fonte e direito de uso da foto da fachada antes de produção.
- Sigla e cursos da Etec (a home usa o que estiver cadastrado).
- Nome: o logo diz "Vitrine CPS Olímpia"; textos usam "Vitrine CPS".
