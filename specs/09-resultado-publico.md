# Spec — Resultado público

- **Responsável**: Guilherme (@guilhermepama), coordenador — `resultados/publico.py`,
  template novo em `resultados/`, `static/css/resultado.css`, `static/js/resultado.js`,
  uma linha em `config/urls.py`
- **Status**: entregue (este PR)
- **Depende de**: ADR-002 (stack), ADR-012 (público pela média bayesiana), ADR-013
  (banca + convidados + público, ranking por curso), spec 04 (resultados), spec 07
  (identidade visual)

> Substitui o item "Página pública de resultado" do "Fora de escopo" da spec 04
> (decisão do PR #14). A coordenação pediu a divulgação pública do ranking com a
> explicação do cálculo depois da edição de 29/10/2026.

## Objetivo
Publicar, no domínio da Vitrine, o resultado oficial da Conexão Fatec de cada edição
divulgada — ranking por curso, notas de cada fonte e como a nota final foi calculada —
para que qualquer pessoa confira a conta.

## Escopo
- Rota pública `GET /resultado/<int:ano>/` → template da edição em
  `resultados/templates/resultados/publico/<ano>.html`, registrado em
  `resultados.publico.DIVULGADOS`. Nesta entrega: só 2026.
- **Página estática**: os números do template são um retrato do resultado oficial
  aprovado pela coordenação. Nesta edição ele veio da planilha da coordenação
  (`notas-fichas-29-10.xlsx`, aba "Ranking"), porque o recálculo do ADR-013 no app
  ainda não está na `main` (falta o PR 3 do ADR-013). As contas foram refeitas a
  partir das notas brutas antes do PR (diferença < 1e-14). As fichas da banca foram
  conferidas pela coordenação em 05/11/2026.
- Conteúdo de 2026:
  - os três primeiros lugares (um por curso: DSM, GTUR, 3º ano do Ensino Médio);
  - a seção "Como calculamos", que abre e fecha (`<details>`);
  - para cada curso: menor e maior nota de cada fonte, a legenda "0 ponto = menor
    nota do curso", e a tabela com posição, banca, convidados, público (média
    ajustada e nº de avaliações), pontos de cada fonte e nota final de 0 a 100;
  - o projeto sem ficha da banca nem dos convidados, "fora do ranking", com o nome
    apresentado no evento e o nome do cadastro.
- Herda `base.html` (topo, menu principal e rodapé). CSS próprio com escopo `.rp` e
  classes `rp-*`; um script pequeno liga/desliga as colunas de pontos.

## Fora de escopo
- Calcular o ranking na view ou ler o banco: a página não consulta nada (o
  resultado divulgado não muda se uma nota for editada depois).
- Notas por avaliador, fichas individuais, qualquer dado por token ou de visitante.
- Ranking geral (todos os cursos juntos): cada curso teve banca e critérios
  próprios (limite aceito no ADR-013); a divulgação é por curso.
- Link no menu principal (precisa caber em 360 px sem JS). A página é divulgada
  pelo link.
- Histórico de edições anteriores e um índice `/resultado/`.

## Comportamento esperado
- Quando o visitante abre `/resultado/2026/`, o sistema mostra a página, sem login e
  sem consulta ao banco.
- Quando o ano não está em `DIVULGADOS` (ex.: 2025, 0), o sistema responde 404.
  Segmento que não é inteiro (`abc`, `-1`) não casa com a rota → 404 (G12).
- POST/PUT/DELETE → 405.
- Sem JavaScript: todas as colunas aparecem e a explicação abre pelo próprio
  `<details>`. Com JavaScript, a caixa "Mostrar os pontos de cada fonte" esconde as
  três colunas de pontos, e um link para `#calculo` abre a explicação.
- No celular (360 px), a página não rola de lado; a tabela larga rola dentro do
  próprio bloco.

## Dados
Não lê nem escreve no banco. Nenhuma migration.

## Endpoints / telas
| Método | Rota | Acesso | Saída | Erros |
|---|---|---|---|---|
| GET | `/resultado/<int:ano>/` | público | HTML do resultado da edição | 404 (ano não divulgado ou inválido), 405 |

## Guardrails aplicáveis
8, 11, 12, 17.

- 8: a página não tem nenhum caminho para votar (teste com as rotas de voto).
- 11: nenhum dado de visitante.
- 12: `ano` só entra pelo conversor `<int:>` e pela lista `DIVULGADOS`.
- 17: testes da rota, dos números e do CSS entregues junto.

## Critérios de aceite
- [x] `/resultado/2026/` responde 200 para anônimo, com os três primeiros lugares e "Como calculamos", em 0 consultas ao banco
- [x] `/resultado/2025/`, `/resultado/0/`, `/resultado/abc/`, `/resultado/-1/` → 404; POST/PUT/DELETE → 405
- [x] Liga `base.css` e `resultado.css`; nenhum link para as rotas de voto (G8)
- [x] Em cada linha das tabelas, pts banca + pts convidados + pts público = nota final (± 0,02 de arredondamento); 28 linhas (DSM 21, GTUR 4, EM 3)
- [x] Notas finais em ordem decrescente em cada curso, com o 1º lugar certo
- [x] Projeto fora do ranking mostra o nome apresentado e o do cadastro
- [x] `resultado.css`: todo seletor começa em `.rp`/`.rp-*`; nenhuma largura fixa > 360 px, `overflow-x: scroll` ou `overflow-wrap: normal`
- [x] Testes do caminho crítico passando

## Perguntas em aberto
Nenhuma.
