# Spec — Credenciamento e votação (dia D)

> Spec de referência: usa o template completo para servir de padrão às demais.

- **Responsável**: Renan (@ReCroffi)
- **Status**: pronta para implementar (ADR-002 aceita: Python + Django)
- **Depende de**: ADR-001, ADR-003, spec 01 (modelo de edições/projetos —
  `Edicao`, `Turma` → edição, `Projeto` com turma e status `publicado`;
  PR #16 em revisão)
- **Usada por**: spec 04 (lê `Estacao.edicao_id`, `Visitante.edicao_id`,
  `tokens`, `votos`, `config_votacao`)

## Objetivo
Permitir que visitantes presentes no evento obtenham uma credencial única
(token) nas estações de QR e votem em quantos projetos quiserem, com no
máximo 1 voto por projeto por token.

## Escopo
- Página `/estacao/<id>` (tela cheia): exibe QR apontando para
  `/entrar?w=<estacao>:<timestamp>&sig=<HMAC>`, regenerado a cada 45s.
- Rota `GET /entrar`: valida assinatura e expiração da janela; emite token
  UUID; grava cookie httpOnly e devolve página que salva em localStorage e
  redireciona ao formulário de visitante.
- Formulário de visitante: nome + email obrigatórios, telefone opcional,
  checkbox de consentimento LGPD; grava em `visitantes` (sem vínculo com o
  token) com a edição em votação e o horário do aceite **truncado para a
  hora**; libera a cédula.
- Cédula `/votar`: lista os projetos com status `publicado` da **edição em
  votação** (projeto → turma → edição), agrupados por turma (categoria);
  botão de voto por projeto; projetos já votados pelo token aparecem
  marcados e desabilitados.
- Rota `POST /votos`: registra voto (token, projeto) em transação atômica,
  só para projeto `publicado` da edição em votação e token emitido por
  estação dessa edição.
- **Estação pertence a uma edição** (`Estacao.edicao_id`): é por ela que o
  token chega à edição.
- Janela de votação: admin abre/encerra, **no máximo uma edição em votação
  por vez**; fora dela, `/entrar`, `/visitantes` e `/votos` recusam.
- **Isolamento por edição**: o ensaio (22/10) é uma edição separada
  ("Ensaio 2026/2"), com turmas, projetos e estações próprios; nada do
  ensaio aparece na edição do evento, e vice-versa.

## Fora de escopo
- Cadastro de projetos, turmas e edições, e o ciclo de status do projeto
  (spec 01).
- Página pública de vitrine (spec 02).
- Relatórios, inclusive o recorte por edição de tokens e visitantes
  (spec 04).
- Painel do admin além de abrir/encerrar votação e cadastrar estações.
- Reabrir votação ou apagar dados para "limpar" o ensaio: o ensaio é outra
  edição (decisão do coordenador no PR #14).
- Registro da decisão do horário truncado na ADR-003 (feito pelo
  coordenador em `docs/02-decisoes.md`).

## Comportamento esperado

### Edição em votação
- **Edição em votação** é a edição cuja `config_votacao` tem
  `aberta_em` ≤ agora e `encerrada_em` vazio ou no futuro. É sempre
  determinada no servidor, a partir de `config_votacao` — nunca de
  parâmetro do cliente nem do token.
- Quando o admin tenta abrir a votação de uma edição enquanto outra está
  em votação, o sistema recusa com a mensagem "Já existe uma votação
  aberta (<edição>). Encerre-a antes de abrir outra." e não grava nada.
- Quando não há edição em votação, `/entrar`, `POST /visitantes` e
  `POST /votos` recusam (ver cada fluxo abaixo) e a cédula mostra só o
  aviso "Votação encerrada", sem lista de projetos.

### Estação e emissão de token
- Toda estação pertence a uma edição (`edicao_id` obrigatório). A edição
  do token é a edição da estação que o emitiu.
- Quando o visitante escaneia o QR dentro da janela de rotação **e** a
  edição da estação é a edição em votação, o sistema emite token e
  redireciona ao formulário.
- Quando o mesmo navegador acessa `/entrar` de novo com cookie de um
  token **existente emitido por estação da mesma edição** do QR, o
  sistema devolve o MESMO token — não cria outro.
- Quando o cookie traz um token de **outra edição** (ex: celular usado no
  ensaio) ou um token que não existe, o sistema ignora o cookie e emite um
  token novo, como num primeiro acesso. O token antigo não é apagado nem
  alterado.
- Quando a assinatura é inválida, a janela expirou, a estação está
  inativa, a estação não é da edição em votação ou não há edição em
  votação, o sistema responde com a mesma página genérica "QR expirado —
  escaneie novamente na estação" (mesmo status HTTP e mesmo corpo).

### Cadastro do visitante
- Quando o visitante envia o formulário válido com votação aberta, o
  sistema grava o cadastro e exibe a cédula. O registro recebe:
  - `edicao_id` = a **edição em votação** no momento do cadastro, lida de
    `config_votacao` — **nunca** a partir do token, do cookie ou da
    estação (guardrail 6, ADR-003; decisão do coordenador no PR #14);
  - `consentimento_em` = horário do servidor **truncado para a hora**
    (minutos, segundos e frações zerados; ex: aceite às 19:42:17 →
    `19:00:00`). Motivo: `tokens.criado_em` e `consentimento_em` gravados
    com segundos de diferença permitiriam cruzar visitante e token pelo
    horário, o vínculo que o G6 e a ADR-003 proíbem. O G10 pede data/hora
    do aceite, não segundos. Decisão do coordenador no PR #14; registro na
    ADR-003 pendente pelo coordenador.
- Nenhum outro campo de data/hora com precisão maior que a hora é gravado
  em `visitantes` (sem `auto_now`/`auto_now_add`, sem `criado_em`).
- Quando falta nome ou email, o email é inválido, algum campo passa do
  tamanho máximo ou o consentimento não foi marcado, o sistema responde
  400 com mensagem genérica de validação, não grava e não libera a cédula
  (guardrail 12).
- Quando o formulário chega sem edição em votação, o sistema não grava e
  responde com a página genérica "QR expirado — escaneie novamente na
  estação".

### Cédula
- Quando o visitante abre `/votar` com token válido da edição em votação,
  o sistema lista só os projetos com status `publicado` cujas turmas
  pertencem à edição em votação (projeto → turma → edição), agrupados por
  turma. Projetos em outro status ou de outra edição não aparecem.
- Projetos já votados por aquele token aparecem marcados e desabilitados.
- Quando não há token, o token não existe ou é de outra edição (via
  estação), o sistema redireciona para a página de instrução ("escaneie o
  QR na estação"), sem dizer qual foi o caso.

### Voto
- Quando o visitante vota num projeto `publicado` da edição em votação,
  ainda não votado por aquele token, com token emitido por estação dessa
  edição, o sistema registra e confirma.
- Quando `projeto_id` não é inteiro positivo, o sistema responde 400 com
  mensagem genérica, sem tocar no banco (guardrail 12).
- Quando ocorre **qualquer** um dos casos abaixo, o sistema não grava e
  responde a MESMA mensagem "voto já registrado", com o mesmo status HTTP
  e o mesmo corpo (guardrail 5):
  - voto duplicado (token, projeto);
  - token ausente ou inexistente;
  - token emitido por estação de outra edição;
  - votação fechada (nenhuma edição em votação);
  - projeto inexistente;
  - projeto com status diferente de `publicado`;
  - projeto de outra edição (turma de outra edição).
- As verificações acima e a inserção acontecem na mesma transação
  atômica; a unicidade continua garantida pela constraint do banco
  (guardrail 4).
- Quando dois requests simultâneos tentam o mesmo (token, projeto), apenas
  um é gravado (constraint no banco, guardrail 4); o outro recebe a
  resposta genérica.

## Dados
Alterações de schema com migration versionada (guardrail 16).
- `tokens`: id (uuid, pk), estacao_id (fk), criado_em. A edição do token
  é `estacoes.edicao_id` — sem coluna própria de edição.
- `votos`: id, token_id (fk), projeto_id (fk), criado_em,
  **unique (token_id, projeto_id)**.
- `visitantes`: id, nome, email, telefone (null), consentimento_em
  (**truncado para a hora**), **edicao_id (fk → `Edicao`, obrigatório,
  preenchido com a edição em votação no cadastro)**.
  **Sem coluna de token, voto ou estação** (guardrail 6). Nenhum outro
  campo de data/hora.
- `estacoes`: id, nome, ativa, **edicao_id (fk → `Edicao`, obrigatório)**.
- `config_votacao`: edicao_id (fk → `Edicao`, único), aberta_em,
  encerrada_em.
- **Lê** da spec 01: `Edicao`; `Turma` (edição); `Projeto` (título,
  turma, status — só `publicado` entra na cédula e no voto).

## Endpoints / telas
| Método | Rota | Entrada | Saída | Erros |
|---|---|---|---|---|
| GET | `/estacao/<id>` | — | HTML com QR autoatualizável | 404 estação inexistente/inativa |
| GET | `/entrar` | `w`, `sig` (query) | redirect p/ formulário + cookie token | página "QR expirado" (assinatura, expiração, estação inativa ou de outra edição, votação fechada) |
| POST | `/visitantes` | nome, email, telefone?, consentimento | redirect p/ cédula | 400 validação; página "QR expirado" se votação fechada |
| GET | `/votar` | cookie/localStorage token | cédula (projetos `publicado` da edição em votação) com estado de votos do token | redirect p/ instrução se sem token, token inexistente ou de outra edição; aviso "Votação encerrada" |
| POST | `/votos` | projeto_id | confirmação | 400 `projeto_id` malformado; "voto já registrado" (genérico) para todas as demais rejeições |

## Guardrails aplicáveis
1, 2, 3, 4, 5, 6, 7, 9, 10, 12, 13, 16, 17.

- 4: verificação de projeto/edição/token e inserção do voto na mesma
  transação; unicidade `(token_id, projeto_id)` no banco.
- 5: projeto não publicado, de outra edição ou inexistente, e token de
  outra edição, caem na mesma resposta genérica das demais rejeições.
- 6: `visitantes.edicao_id` vem de `config_votacao`, nunca do token;
  `consentimento_em` truncado para a hora impede o cruzamento pelo
  horário; nenhum outro timestamp em `visitantes`.
- 9: `edicao_id` não é dado pessoal; nenhum campo pessoal novo.
- 10: o aceite continua registrado com data e hora (hora cheia), junto ao
  cadastro.
- 12: `projeto_id` validado como inteiro positivo antes do banco; campos
  do formulário com tipo e tamanho validados.

## Critérios de aceite

**Emissão e janela**
- [ ] QR da estação muda sozinho a cada 45s sem recarregar manualmente
- [ ] URL capturada deixa de emitir token após a expiração da janela
- [ ] Re-scan no mesmo navegador devolve o mesmo token (cookie)
- [ ] Com votação encerrada, `/entrar`, `POST /visitantes` e `/votos` recusam
- [ ] Abrir a votação de uma edição com outra edição em votação é recusado e não altera nenhuma `config_votacao`

**Visitante**
- [ ] Formulário sem nome/email ou sem consentimento não libera cédula (400)
- [ ] `visitantes` não tem nenhuma coluna ligando ao token, voto ou estação (revisão de schema)
- [ ] Visitante cadastrado recebe `edicao_id` da edição em votação; teste com cookie de token de **outra** edição presente no request mostra que o `edicao_id` gravado continua o da edição em votação
- [ ] O código do cadastro de visitante não lê token, cookie nem estação (revisão de código)
- [ ] Aceite às 19:42:17 grava `consentimento_em` = 19:00:00 do mesmo dia (minutos, segundos e microssegundos zerados)
- [ ] `visitantes` não tem outro campo de data/hora além de `consentimento_em` (revisão de schema: sem `auto_now`/`auto_now_add`)

**Cédula e voto**
- [ ] Cédula lista só projetos `publicado` da edição em votação: projeto em `em_revisao` da mesma turma e projeto `publicado` de outra edição não aparecem
- [ ] Segundo voto no mesmo projeto pelo mesmo token é recusado com mensagem genérica
- [ ] POST de voto em projeto não `publicado`, em projeto de outra edição, em projeto inexistente, com token de outra edição, com token inexistente e com votação fechada → resposta idêntica (status e corpo) à do voto duplicado, e nenhum voto gravado
- [ ] `projeto_id` não inteiro (`abc`, `1.5`, vazio) → 400 genérico, nenhuma query de voto
- [ ] Teste de corrida: 2 POSTs simultâneos (mesmo token+projeto) → 1 voto no banco

**Isolamento por edição** (fixture com a edição do evento e a edição "Ensaio", cada uma com turma, projetos e estação próprios)
- [ ] Token emitido por estação do ensaio não vota em projeto do evento (resposta genérica, nenhum voto gravado)
- [ ] Re-scan no evento com cookie de token do ensaio emite token **novo**, ligado a estação do evento; o token do ensaio continua intacto
- [ ] Votos do ensaio não aparecem como votados na cédula do evento (e vice-versa)
- [ ] Visitante cadastrado durante a votação do ensaio fica com `edicao_id` do ensaio; durante a do evento, com o do evento
- [ ] Encerrar o ensaio e abrir o evento não altera nem apaga tokens, votos ou visitantes do ensaio

- [ ] Testes do caminho crítico passando (emissão, unicidade, rejeições, isolamento)

## Decisões do coordenador incorporadas (PR #14)
- Cédula e voto só com projetos `publicado` — mesmo filtro do ranking da
  spec 04 (resposta 7).
- O ensaio é outra edição ("Ensaio 2026/2"), com turmas, projetos e
  estações próprios; nada de reabrir votação ou apagar dados (resposta 8).
- `Estacao` ganha `edicao_id` e os tokens chegam à edição pela estação;
  `Visitante` ganha `edicao_id` direto, preenchido pela edição em votação,
  nunca pelo token (resposta 13).
- `visitantes.consentimento_em` gravado truncado para a hora ("Ponto para
  a spec 03"); registro na ADR-003 pendente pelo coordenador.

## Perguntas em aberto
- Intervalo exato de rotação (45s é proposta) e tolerância de relógio.
- Texto final do consentimento LGPD (coordenação).
- **Uma edição em votação por vez**: esta spec impede abrir uma votação
  com outra aberta, porque `Visitante.edicao_id` depende de existir uma
  única edição em votação. Confirmar com o coordenador (ensaio e evento
  não se sobrepõem no cronograma).
- **Correlação residual visitante × token** (não trava a spec, mas pede
  posição do coordenador): mesmo com a hora truncada, (a) o `id`
  sequencial de `visitantes` segue a ordem de cadastro, que se aproxima
  da ordem de `tokens.criado_em` dentro da mesma hora; (b) o log de
  acesso do servidor web (ADR-006) registra `GET /entrar` e
  `POST /visitantes` com segundos e IP. Opções: id não sequencial (UUID)
  em `visitantes` e/ou log de acesso sem esses caminhos ou com retenção
  curta.
- Nomes finais dos campos de `Edicao`, `Turma` e `Projeto` dependem da
  spec 01 (PR #16); esta spec usa `Turma` → edição, `Projeto.turma` e
  `Projeto.status = publicado`. Ajustar se o PR #16 mudar algum nome.
