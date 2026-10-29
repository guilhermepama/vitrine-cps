# Spec — Mapa do evento

- **Responsável**: Guilherme (@guilhermepama), coordenador — app novo
  `mapa/`, uma linha em `config/settings.py` e em `config/urls.py`,
  bloco novo no `base.css`, `pytest.ini` (testpaths)
- **Status**: entregue (PR #95)
- **Depende de**: ADR-002 (stack), ADR-015 (aceita: planta fixa em
  código, conteúdo no banco), spec 01 (`Edicao`, `Projeto`), spec 07
  (identidade visual)

## Objetivo
Dar ao visitante da Conexão Fatec um mapa de evento — como em feiras e
convenções — para achar os estandes dos alunos no corredor e as atrações
nas salas, impresso ao lado de cada estação de QR ("você está aqui") e
aberto no celular.

## Escopo
- **Planta fixa em código** (`mapa/planta.py`): o prédio da Fatec Olímpia
  desenhado a partir da planta do Figma (`PLANTA_FATEC_OLIMPIA.fig`):
  corredor central, 7 salas + sala VIP, secretaria, TI, biblioteca, apoio e WC
  no lado **A**; 10 salas, cozinha, refeitório e WC no lado **B**; entrada do público pela passagem lateral; 31
  estandes no corredor (15 na fileira A, 16 na fileira B); 4 pontos de
  estação de QR. Cada ponto tem um `codigo` estável (`a01`, `sala-a-03`,
  `qr-entrada`…), posição e tamanho.
- **Conteúdo no banco** (`mapa.Local`, um por ponto e por edição):
  rótulo exibido, nome da atração, descrição curta, porta aberta/fechada
  e, no estande, o projeto que está nele.
- **Comando `semear_mapa`**: cria os `Local` da edição ativa a partir da
  planta (idempotente: não sobrescreve o que já foi editado). Opção
  `--fileiras A,B` (padrão) ou `--fileiras D,E` muda só a letra das
  fileiras e os rótulos dos estandes.
- **Admin** `Local` com edição em lista (rótulo, nome, aberta, projeto):
  é a tela usada na montagem do espaço, no dia anterior ao evento.
- **Página pública `GET /mapa/`**: mapa em SVG (paisagem em telas
  largas e impressão; retrato no celular, com o visitante "subindo" o
  corredor a partir da entrada), legenda, lista de estandes com o
  projeto de cada um (link para a página do projeto) e lista de salas
  abertas com a atração. `?aqui=<codigo>` destaca o ponto "Você está
  aqui" (código inválido é ignorado, sem erro).
- **Impressão**: `@media print` em paisagem, só o mapa e as listas
  (topo e rodapé já ficam fora pela classe `nao-imprime`).

## Fora de escopo
- Alterar a tela da estação (`/estacao/<id>`), congelada e do Renan: o
  mapa fica impresso ao lado da TV, não dentro dela.
- Editor gráfico da planta; mover pontos é editar `mapa/planta.py`.
- Programação por horário das atrações (ADR-011, próxima edição).
- Link no menu principal (precisa caber em 360 px sem JS; fica para
  depois do evento). A página é alcançada pelo QR impresso, pela
  Semana da Tecnologia e pela URL.

## Comportamento esperado
- Quando não há edição ativa ou os `Local` não foram semeados, `/mapa/`
  responde 200 com a planta vazia (só salas e serviços fixos) e o aviso
  "mapa em montagem".
- Estande com projeto: mostra o rótulo no mapa e, na lista, rótulo +
  título + curso/turma com link para `/projeto/<slug>/`. Só projetos
  `publicado` entram na lista; estande com projeto em outro status
  aparece no mapa como ocupado, sem link.
- Estande sem projeto: desenhado vazio (contorno), sem entrada na lista.
- Estande sem projeto com nome preenchido (expositor, ex.: Secretaria de
  Turismo) aparece em "Salas e atrações" e é desenhado como ocupado; com
  projeto, o nome livre é ignorado.
- Sala aberta: destacada, com o nome da atração no mapa (abreviado) e na
  lista. Sala fechada: cinza, só o rótulo, fora da lista.
- Serviços (secretaria, biblioteca, WC, cozinha): sempre desenhados, não
  entram nas listas; secretaria/TI/biblioteca podem receber atração como
  qualquer sala.
- `?aqui=qr-02`: o ponto ganha o marcador vermelho "Você está aqui" nas
  duas orientações e no título da impressão.
- `?aqui=` só marca estação de QR; outro ponto válido é tratado como
  ausente.
- Projeto só em estande e só da mesma edição (validação do model).
- Nenhum `href`, `action` ou `src` da página aponta para `/entrar`,
  `/estacao`, `/votar`, `/votos` ou `/visitantes` (G8).
- Número de queries constante (dois `select` + `select_related`).

## Dados
Tabela `mapa_locais` (`mapa.Local`), migration `mapa/0001`:

| campo | tipo | nota |
|---|---|---|
| `edicao` | FK `Edicao` PROTECT | |
| `codigo` | slug 20 | único com `edicao`; chave para `planta.py` |
| `tipo` | choices `estande`, `sala`, `servico`, `passagem`, `estacao`, `entrada` | copiado da planta |
| `fileira` | char 1, vazio | `A`/`B` (ou `D`/`E`) nos estandes |
| `ordem` | smallint | ordem a partir da entrada |
| `rotulo` | char 20 | o que o visitante lê: "A3", "Sala 12" |
| `nome` | char 80, vazio | atração da sala ou nome livre |
| `descricao` | char 200, vazio | |
| `aberta` | bool, padrão True | porta aberta/fechada |
| `projeto` | FK `Projeto` SET_NULL, null | só em `estande`; um projeto em no máximo um estande por edição (unique `edicao`+`projeto`) |

Não lê nem escreve nada de `votacao`, `banca` ou `resultados`.

## Endpoints / telas
- `GET /mapa/` → 200, `<title>` "Mapa do evento — Vitrine Fatec".
  Query opcional `aqui` (slug, até 20 caracteres; outro valor é tratado
  como ausente).
- Admin: `/admin/mapa/local/`, lista por edição com `list_editable`.
- Comando: `python manage.py semear_mapa [--edicao NOME] [--fileiras A,B]`.

## Guardrails aplicáveis
8 (nenhum caminho de voto), 12 (`aqui` validado como slug), 13 (só ORM),
15 (admin só para superusuário, como os demais), 16 (migration no
repositório), 17 (testes).

## Critérios de aceite
- [x] `semear_mapa` cria 31 estandes, 18 salas (17 + VIP), 8 serviços, a passagem
      da entrada lateral, 4 estações e a entrada (63 pontos)
      para a edição ativa; rodar de novo não duplica nem apaga edições
- [x] `--fileiras D,E` gera `D1…D12` e `E1…E16`
- [x] `GET /mapa/` 200 com e sem edição ativa; com o aviso quando vazio
- [x] Estande com projeto publicado lista o título com link; sala fechada
      não mostra o nome da atração; sala aberta mostra
- [x] `?aqui=` válido marca "Você está aqui"; inválido não quebra
- [x] HTML sem `style=`; `base.css` continua sem largura fixa > 360 px
- [x] Nenhum link de voto (G8)
- [x] Um projeto não pode estar em dois estandes da mesma edição
- [x] Testes do caminho crítico passando

## Perguntas em aberto
- Numeração real das salas (porta): confirmada na montagem, 28/10, e
  digitada no admin.
- Quantidade e posição definitiva das estações de QR (a planta prevê 4:
  entrada, meio do corredor em dois pontos e perto da secretaria).
