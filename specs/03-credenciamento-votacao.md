# Spec — Credenciamento e votação (dia D)

> Spec de referência: usa o template completo para servir de padrão às demais.

- **Responsável**: Renan (@ReCroffi)
- **Status**: pronta para implementar — revisões do coordenador nos PRs
  #18 e #20 aplicadas (ADR-002 aceita: Python + Django)
- **Depende de**: ADR-001, ADR-003, ADR-006 (logs da hospedagem e
  cabeçalho do IP real em `DJANGO_IP_HEADER`, até 08/10),
  `cadastro/seguranca.py` (na `main`, PR #25: `ip_do_cliente` e
  `chave_ip`), spec 01 (na `main`, PRs #16 e #17:
  `Edicao` com `votacao_aberta_em` e `votacao_encerrada_em`,
  `Turma.edicao`, `Projeto.turma`, `Projeto.status`)
- **Usada por**: spec 04 (lê `Estacao.edicao_id`, `Visitante.edicao_id`,
  `Token`, `Voto` e os campos de votação da `Edicao`)

## Objetivo
Permitir que visitantes presentes no evento obtenham uma credencial única
(token) nas estações de QR e votem em quantos projetos quiserem, com no
máximo 1 voto por projeto por token.

## Escopo
- Página `/estacao/<id>` (tela cheia): exibe QR apontando para
  `/entrar?w=<estacao>:<timestamp>&sig=<HMAC>`, regenerado a cada 45s.
  Só para usuário staff logado com a permissão `votacao.operar_estacao`
  — ver "Acesso à página da estação".
- Redirects de `/votar` sem token válido para `/como-votar/`
  (`vitrine:como_votar`, spec 02), a página de explicação do voto
  presencial definida na spec 02 (PR #23, app `vitrine`) — esta spec não
  define essa página (guardrail 8).
- Rota `GET /entrar`: valida assinatura e expiração da janela; emite token
  UUID; grava cookie httpOnly e devolve página que salva em localStorage e
  redireciona ao formulário de visitante (`GET /visitantes`), que manda
  direto à cédula quem já tem cadastro válido.
- Rate limit da emissão em duas camadas — por janela de estação e por IP
  (guardrail 7, ADR-001; ver "Rate limit da emissão").
- Formulário de visitante: nome + email obrigatórios, telefone opcional,
  checkbox de consentimento LGPD; grava em `visitantes` (sem vínculo com o
  token) com a edição em votação e o horário do aceite **truncado para a
  hora**; libera a cédula por um **cookie de cadastro** que não identifica
  o visitante (ver "Liberação da cédula").
- Cédula `/votar`: lista os projetos com status `publicado` da **edição em
  votação** (projeto → turma → edição), agrupados por turma (a turma é a
  categoria — spec 01); botão de voto por projeto; projetos já votados
  pelo token aparecem marcados e desabilitados.
- Rota `POST /votos`: registra voto (token, projeto) em transação atômica,
  só para projeto `publicado` da edição em votação e token emitido por
  estação dessa edição.
- **Estação pertence a uma edição** (`Estacao.edicao_id`): é por ela que o
  token chega à edição. A edição da estação não muda depois da primeira
  emissão.
- Abrir/encerrar votação: a spec 03 preenche `Edicao.votacao_aberta_em` e
  `Edicao.votacao_encerrada_em` (spec 01), por ações no admin do app
  `votacao`; **no máximo uma edição em votação por vez**; edição encerrada
  não é reaberta.
- Admin de estações (cadastrar, ativar/desativar).
- **Isolamento por edição**: o ensaio (22/10) é uma edição separada
  ("Ensaio 2026/2"), com turmas, projetos e estações próprios; nada do
  ensaio aparece na edição do evento, e vice-versa.
- Filtro de log do app `votacao` para as rotas do visitante (ver
  "Correlação visitante × token (B1)").

## Fora de escopo
- Cadastro de projetos, turmas e edições, o ciclo de status do projeto e
  as travas depois de abrir a votação (spec 01).
- Página pública de vitrine (spec 02).
- Relatórios, inclusive o recorte por edição de tokens e visitantes
  (spec 04).
- Reabrir votação ou apagar dados para "limpar" o ensaio: o ensaio é outra
  edição (decisão do coordenador no PR #14). A tentativa de reabrir é
  recusada (ver "Abrir e encerrar").
- Registro da decisão do horário truncado na ADR-003 (do coordenador,
  em `docs/02-decisoes.md`, no PR da importação — cadastro 2/3).
- `settings.py` (`LOGGING` e a leitura do `IP_HMAC_SECRET`),
  `.env.example` e configuração de log da hospedagem: são do
  coordenador; esta spec entrega o filtro e diz o que precisa ser ligado.
- Escolha do servidor e do cabeçalho que traz o IP real atrás do proxy
  (ADR-006, coordenador, até 08/10) — o valor de `DJANGO_IP_HEADER`,
  lido por `cadastro/seguranca.py`.
- Permissões de admin além do superusuário (mesma regra da spec 01 nesta
  edição). A única permissão própria desta spec é
  `votacao.operar_estacao`, que não dá acesso a nenhum model no admin
  (ver "Acesso à página da estação").

## Comportamento esperado

### Edição em votação
- **Edição em votação** é a edição com `votacao_aberta_em` preenchido e
  `votacao_encerrada_em` vazio. É sempre determinada no servidor, a partir
  da `Edicao` — nunca de parâmetro do cliente nem do token.
- Quando não há edição em votação, `/entrar`, `POST /visitantes` e
  `POST /votos` recusam (ver cada fluxo abaixo) e a cédula mostra só o
  aviso "Votação encerrada", sem lista de projetos.
- **Referência temporal** (G4): emissão, cadastro e voto leem a edição em
  votação com `select_for_update()` na linha da `Edicao`, dentro da
  transação da operação; abrir e encerrar também travam essa linha. Assim
  cada operação acontece inteira antes ou inteira depois do encerramento:
  - operação que obteve a trava antes do encerramento é concluída e conta;
  - operação que espera a trava e a obtém depois do encerramento vê a
    votação fechada e é recusada como "votação fechada".
  Custo aceito: as operações de uma edição ficam serializadas nessa linha
  (transações curtas, volume de um evento presencial). A trava no voto
  será **medida no pré-ensaio de 21/10**. Plano B, **não implementar
  agora**: se ficar lento, o voto deixa de travar a `Edicao` e a spec 04
  conta só votos com `criado_em` antes de `votacao_encerrada_em`
  (decisão do coordenador no PR #18).

### Abrir e encerrar (admin)
- Ações no admin do app `votacao`, sobre um proxy de `Edicao` ("Votação
  por edição", sem tabela própria): **Abrir votação** e **Encerrar
  votação**, uma edição por vez. Só superusuário vê e executa; staff não
  superusuário (ex: grupo `digitacao-banca`, spec 06) não vê o menu e
  recebe 403 se chamar a ação pela URL; anônimo vai para o login (G15).
- **Abrir**: em uma transação, trava todas as linhas de `Edicao`
  (`select_for_update()` ordenado por `pk`), confere as regras e grava
  `votacao_aberta_em = agora` na instância travada com `edicao.save()`.
  Recusa, sem gravar nada:
  - outra edição em votação → "Já existe uma votação aberta (<edição>).
    Encerre-a antes de abrir outra.";
  - `votacao_aberta_em` já preenchido (edição aberta ou encerrada) →
    "A votação desta edição já foi aberta e não pode ser reaberta."
    (`votacao_aberta_em` não muda depois de preenchido — spec 01).
- **Encerrar**: em uma transação, trava a linha da edição
  (`select_for_update()`) e grava `votacao_encerrada_em = agora` na
  instância travada com `edicao.save()`. Recusa, sem gravar nada, se a
  votação não foi aberta ou já foi encerrada. A spec 03 nunca apaga nem
  altera `votacao_encerrada_em` depois de preenchido.
- **Só via `save()`**: campos travados da `Edicao` mudam só por `save()`
  ou métodos do model, **nunca `QuerySet.update()`**, que passa por cima
  das travas (regra do coordenador no PR #17). Abrir e encerrar não usam
  `Edicao.objects.filter(...).update(...)` nem `bulk_update`.
- Os dois campos ficam somente leitura em todas as telas (spec 01); só as
  ações acima os preenchem.

### Estação
- Toda estação pertence a uma edição (`edicao_id` obrigatório). A edição
  do token é a edição da estação que o emitiu.
- Admin de estações (superusuário): nome, edição, ativa. Estação que já
  emitiu token **não muda de edição** (validação no model, `ValidationError`
  — senão os tokens antigos passariam a contar para outra edição) e
  **não pode ser apagada** (`PROTECT` em `Token.estacao`); para tirá-la de
  uso, desativa-se.
- `Voto.token`, `Voto.projeto`, `Estacao.edicao` e `Visitante.edicao`
  também são `PROTECT`: nada do ensaio ou do evento é apagado em cascata.

### Acesso à página da estação
- **Problema**: sem login, qualquer pessoa, de casa, abre `/estacao/1` e
  lê QRs válidos o tempo todo. A exigência de presença física (ADR-001:
  estações supervisionadas) cai, e o único freio passa a ser o rate
  limit — 20 tokens por janela de 45s, cerca de 1.600 tokens por hora por
  estação.
- **Regra**: a página exige usuário **logado, ativo, com `is_staff` e com
  a permissão `votacao.operar_estacao`** (decisão do coordenador no PR
  #20).
  - `votacao.operar_estacao` é permissão própria, declarada em
    `Estacao.Meta.permissions` (migration do app `votacao`), com o nome
    "Pode operar a página da estação". É dada a um grupo "estação",
    criado pelo superusuário no admin; a conta do notebook/tablet da
    estação entra nesse grupo e em nenhum outro. A permissão não dá
    acesso a nenhum model no admin.
  - **Por que a permissão, e não só `is_staff`**: a equipe de digitação
    da banca (grupo `digitacao-banca`, spec 06) também é staff. Só com
    `is_staff`, qualquer conta da digitação abriria a estação e geraria
    QRs.
  - **Por que `is_staff` continua**: o login usado é o do admin
    (`admin:login`), que recusa usuário não staff. Sem `is_staff`, a conta
    da estação não consegue logar.
  - Superusuário tem todas as permissões e passa pela regra.
  - O staff fica ao lado da tela. Não muda permissões de admin (ver "Fora
    de escopo").
- **Ordem**: a autenticação é conferida **antes** de buscar a estação,
  para não revelar quais ids existem.
  - Anônimo → redirect (302) para o login do admin (`admin:login`) com
    `next=/estacao/<id>`; nenhum QR, `w` ou `sig` no corpo. Usa o login
    do admin para não depender de `LOGIN_URL` no `settings.py`.
  - Logado sem `is_staff`, ou staff sem `votacao.operar_estacao` →
    **404**, corpo igual ao da estação inexistente. Os dois casos têm a
    mesma resposta.
  - Staff com a permissão → as regras de sempre: estação inexistente ou
    inativa → 404; senão, a tela com o QR.
- A renovação automática do QR (qualquer requisição da estação que
  devolva QR, `w` ou `sig`) segue a mesma regra; se a sessão do staff
  cair, a tela deixa de mostrar QR em vez de exibir um QR velho.
- Respostas da estação com `Cache-Control: no-store` (o QR não fica em
  cache do navegador nem de proxy).
- A sessão do Django só existe no aparelho da estação (login do staff).
  As rotas do visitante continuam sem sessão (ver "Liberação da cédula").
- Limite aceito: quem tiver a senha da conta da estação abre a estação de
  qualquer lugar; essa conta é tratada como credencial do evento (senha
  forte, troca depois do evento).

### Formulário de visitante
- `GET /visitantes`: mostra o formulário de visitante (nome, email,
  telefone, consentimento, com o texto do consentimento). É o destino do
  redirect de `/entrar`. Como o cadastro, **não lê** o cookie do token, o
  localStorage nem a estação; query string ignorada. Sem edição em
  votação → página genérica "QR expirado — escaneie novamente na estação"
  (400), a mesma do `POST /visitantes`, para ninguém preencher um
  formulário que será recusado. Não grava nada (nem sessão, nem cache).
- `GET /visitantes` com **cookie de cadastro válido** (ver "Liberação da
  cédula") → redirect (302) para a cédula (`/votar`), sem mostrar o
  formulário. Evita cadastro duplicado de quem volta ao formulário (botão
  voltar, link salvo) — decisão do coordenador no PR #20. O único cookie
  lido é o de cadastro.
- `/como-votar/` (`vitrine:como_votar`) é da spec 02 (PR #23, app
  `vitrine`): esta spec só redireciona para lá a partir de `GET /votar`.

### Emissão de token
- **Rotação e tolerância**: a estação gera QR novo a cada 45s; `/entrar`
  aceita `timestamp` entre agora − 90s e agora + 5s (a janela atual e a
  anterior, mais folga para o caminho do celular). O `timestamp` é gerado
  pelo próprio servidor, então não há relógio de estação a tolerar
  (decisão do coordenador no PR #18).
- Quando o visitante escaneia o QR dentro da janela de rotação **e** a
  edição da estação é a edição em votação, o sistema emite token e
  redireciona ao formulário (ou direto à cédula, se o cookie de cadastro
  da mesma edição estiver presente — ver "Liberação da cédula").
- Quando o mesmo navegador acessa `/entrar` de novo com cookie de um
  token **existente emitido por estação da mesma edição** do QR, o
  sistema devolve o MESMO token — não cria outro.
- Quando o cookie traz um token de **outra edição** (ex: celular usado no
  ensaio), um token que não existe ou um valor que não é UUID válido, o
  sistema ignora o cookie e emite um token novo, como num primeiro
  acesso. O token antigo não é apagado nem alterado.
- Quando a entrada é malformada (ver "Validação de entrada"), a
  assinatura é inválida, a janela expirou, a estação não existe, está
  inativa ou não é da edição em votação, não há edição em votação, ou o
  rate limit estourou (ver abaixo), o sistema responde com a mesma página
  genérica "QR expirado — escaneie novamente na estação", **status 400 e
  corpo idêntico** em todos os casos.

### Rate limit da emissão (guardrail 7)
Uma das duas camadas da ADR-001 contra o link do QR repassado (ex:
WhatsApp). Decisão do coordenador no PR #18.
- **Ordem em `/entrar`**: validação de entrada → assinatura e janela →
  transação com a trava da `Edicao` → rate limit → estação → token. Só a
  requisição com entrada válida, assinatura correta, janela no prazo e
  edição em votação conta nos contadores (assinatura forjada não esgota a
  janela de uma estação); conta mesmo quando devolve o mesmo token
  (re-scan). O rate limit fica **dentro** da trava da `Edicao`: fora
  dela, requisições simultâneas leriam a mesma contagem e todas
  passariam.
- **Por janela de estação** (a camada que importa): no máximo **20
  tokens por janela de 45s por estação**, isto é, por estação e bloco
  de 45 s do `timestamp` (`estacao_id` e `timestamp // 45`, lidos do `w`
  já validado e assinado). Um QR fotografado e repassado esgota rápido.
  Cada bloco tem contador próprio; estações diferentes não se afetam
  (decisão 1 do coordenador no PR #31).
- **Por IP, generoso**: no máximo **300 emissões por 10 min por IP**. No
  evento quase todos saem pelo mesmo IP do Wi-Fi da Fatec; o limite só
  barra script.
- **IP real**: o IP do cliente vem **só** de
  `ip_do_cliente(request)`, de `cadastro/seguranca.py` (PR #25,
  compartilhado com a spec 02). Atrás do proxy da hospedagem,
  `REMOTE_ADDR` é o IP do proxy; o cabeçalho com o IP real é a variável
  de ambiente `DJANGO_IP_HEADER` (`settings.IP_HEADER`), de
  responsabilidade do coordenador (ADR-006, até 08/10). Vazia
  (desenvolvimento, CI), a função usa `REMOTE_ADDR`; em lista
  (`X-Forwarded-For`), vale o último item. **O código do app `votacao`
  nunca lê `REMOTE_ADDR`, `X-Forwarded-For` nem outro cabeçalho de IP
  direto** — trocar o cabeçalho é mudar a variável, não o código.
- **A chave do IP no cache é o HMAC-SHA256 do IP, nunca o IP em claro**,
  com expiração (10 min); o IP não vai para log nem para tabela de model
  (coerente com P2). Motivo: a tabela do `DatabaseCache` entra no
  `pg_dump` com o horário de expiração, que dá o horário da emissão; com
  o IP em claro, o dump ligaria IP e horário. Recomendação do coordenador
  no PR #18.
  - Segredo próprio em variável de ambiente, `IP_HMAC_SECRET` (no padrão
    do `RA_HMAC_SECRET` da spec 01); **não reutiliza** o
    `QR_HMAC_SECRET` nem o `RA_HMAC_SECRET`. Obrigatória: sem ela, a
    aplicação não sobe.
  - Chave: `"rl:entrar:ip:" + chave_ip(ip_do_cliente(request))`.
    `chave_ip(texto)`, de `cadastro/seguranca.py`, devolve o
    HMAC-SHA256 em hex com `IP_HMAC_SECRET` do IP normalizado: IPv4 como
    está; IPv6 agrupado pelo prefixo /64 (um aparelho troca de endereço
    dentro do seu /64 e furaria o limite); IP ausente ou inválido → chave
    fixa, que divide um único contador (o limite fica mais apertado,
    nunca mais frouxo). O app `votacao` não calcula HMAC de IP por conta
    própria. O IP em claro só existe em memória durante a requisição.
  - Ler o segredo e o cabeçalho no `settings.py` e declará-los no
    `.env.example` é do coordenador (já na `main`, PRs #24 e #25; ver
    "Fora de escopo").
- **Contadores no `DatabaseCache`** já configurado no esqueleto
  (`CACHES["default"]`, compartilhado entre os workers). Chave da janela
  expira com a tolerância do QR (150s). Leitura e gravação do contador
  não são atômicas no `DatabaseCache`; por isso a contagem acontece com a
  linha da `Edicao` travada (`select_for_update()` da emissão), que
  enfileira as emissões da edição: duas requisições simultâneas não leem
  a mesma contagem e o limite vale também sob rajada.
- **Estourou** → a mesma página "QR expirado", **400, corpo idêntico** ao
  da assinatura inválida; nada revela que foi o limite. Não emite token
  nem conta nos contadores.
- Não remover nem afrouxar "para testar" (guardrail 7): testes ajustam o
  contador, não desligam o limite.

### Cadastro do visitante
- Quando o visitante envia o formulário válido com votação aberta, o
  sistema grava o cadastro, grava o cookie de cadastro e redireciona à
  cédula. O registro recebe:
  - `edicao_id` = a **edição em votação** no momento do cadastro, lida da
    `Edicao` — **nunca** a partir do token, do cookie ou da estação
    (guardrail 6, ADR-003; decisão do coordenador no PR #14);
  - `consentimento_em` = horário do servidor **truncado para a hora**
    (minutos, segundos e microssegundos zerados). O truncamento é feito no
    fuso `America/Sao_Paulo` (`TIME_ZONE` do projeto) e o valor é gravado
    em UTC (`USE_TZ = True`); como o deslocamento é de horas inteiras
    (−03:00, sem horário de verão), dá o mesmo instante que truncar em
    UTC. Ex: aceite às 19:42:17 de 25/10/2026 em Brasília (22:42:17 UTC)
    → gravado 25/10/2026 19:00:00 em Brasília (22:00:00 UTC).
    Motivo: `tokens.criado_em` e `consentimento_em` gravados com segundos
    de diferença permitiriam cruzar visitante e token pelo horário, o
    vínculo que o G6 e a ADR-003 proíbem; o G10 pede data/hora do aceite,
    não segundos. Decisão do coordenador no PR #14; o registro na ADR-003
    é do coordenador, no PR da importação (cadastro 2/3). O truncamento **reduz** a precisão desse
    caminho, mas **não impede sozinho** o cruzamento: numa hora com poucos
    cadastros ainda há inferência, e ordem de cadastro e logs são outros
    caminhos — ver "Correlação visitante × token (B1)".
- Nenhum outro campo de data/hora é gravado em `visitantes` (sem
  `auto_now`/`auto_now_add`, sem `criado_em`).
- O cadastro **não lê** o cookie do token, o localStorage nem a estação.
- **Texto do consentimento (provisório)**, no template do formulário:
  "Aceito que o Centro Paula Souza (Fatec e Etec Olímpia) use meu nome,
  e-mail e telefone para enviar comunicações sobre eventos e cursos."
  O texto final vem da coordenação até 20/10; trocar o texto não muda
  código nem dados (decisão do coordenador no PR #18).
- Quando algum campo falha na validação (ver "Validação de entrada"), o
  sistema responde 400, reapresenta o formulário com a mensagem genérica
  "Não foi possível concluir o cadastro. Confira os campos.", não grava,
  não grava o cookie de cadastro e não libera a cédula (guardrail 12).
- Quando o formulário chega sem edição em votação, o sistema não grava e
  responde com a página genérica "QR expirado — escaneie novamente na
  estação" (400).
- Quando o formulário válido chega com **cookie de cadastro válido** da
  edição em votação (aba antiga, reenvio), o sistema redireciona (302) à
  cédula **sem gravar** novo registro nem regravar o cookie — a mesma
  regra do `GET`. A conferência vem **depois** da validação do formulário
  e **dentro** da transação, com a `Edicao` travada (decisão do
  coordenador no PR #33). O toque duplo no botão não é coberto (os dois
  envios saem antes do cookie chegar); só o cliente evitaria.
- **Rate limit** (decisão do coordenador no PR #33; fatia F5b, depois da
  F4): no máximo **300 envios por 10 min por IP**, o mesmo limite do
  `/entrar`, com o contador na chave de `chave_ip(ip_do_cliente(request))`
  no `DatabaseCache`, conferido **antes** da trava da `Edicao`. Estouro →
  400 com o formulário e a mesma mensagem genérica, nada gravado. Motivo:
  sem limite, um script enche `visitantes` de contatos falsos (ADR-003) e
  cada envio disputa a trava da `Edicao` com `/entrar` e `/votos`.

### Liberação da cédula (sem vínculo visitante × token)
- Cadastro concluído grava um **cookie de cadastro**: valor =
  `edicao_id` da edição em votação, assinado com
  `django.core.signing.Signer` (salt `votacao.cadastro`, **sem
  timestamp** — não usar `signing.dumps`/`TimestampSigner`); httpOnly,
  `Secure`, `SameSite=Lax`, validade de 1 dia.
- O valor é o mesmo para todos os visitantes da edição: não carrega id do
  visitante, do token, horário nem número aleatório. O servidor não grava
  nada que ligue o cadastro ao token: **não usar a sessão do Django**
  (tabela de sessão), cache, nem qualquer tabela para esse estado. (Os
  únicos registros no cache são os contadores do rate limit de
  `/entrar`, que não carregam token nem visitante.)
- Cookie de cadastro **válido** = assinatura correta e `edicao_id` igual
  ao da edição em votação. Qualquer outro caso (ausente, adulterado, de
  outra edição) = sem cadastro.
- `GET /votar` com token válido e **sem** cadastro válido → redirect para
  o formulário de visitante.
- `POST /votos` sem cadastro válido → rejeição genérica (ver "Voto").
- Re-scan na mesma edição com cadastro válido → vai direto à cédula, sem
  novo registro em `visitantes`. O mesmo vale para `GET /visitantes` com
  cadastro válido (ver "Formulário de visitante").
- Troca ensaio → evento: o cookie de cadastro do ensaio não vale no
  evento; o visitante preenche o formulário de novo e ganha um registro
  com `edicao_id` do evento (é visitante das duas edições).
- Limite aceito: o cookie de cadastro pode ser copiado entre navegadores.
  O cadastro é para captação de contatos (ADR-003), não controle de
  acesso; o controle de acesso é o token, que só sai pelo QR.

### Cédula
- Quando o visitante abre `/votar` com token válido da edição em votação
  e cadastro válido, o sistema lista só os projetos com status
  `publicado` cujas turmas pertencem à edição em votação (projeto → turma
  → edição), agrupados por turma. Projetos em outro status ou de outra
  edição não aparecem.
- Projetos já votados por aquele token aparecem marcados e desabilitados.
- Quando não há token, o token é malformado, não existe ou é de outra
  edição (via estação), o sistema redireciona para `/como-votar/`
  (`vitrine:como_votar`, spec 02), sem dizer qual foi o caso.

### Voto
- Quando o visitante vota num projeto `publicado` da edição em votação,
  ainda não votado por aquele token, com token emitido por estação dessa
  edição e cadastro válido, o sistema registra e responde **201**, JSON
  `{"status": "registrado"}`.
- Quando `projeto_id` é malformado (ver "Validação de entrada"), o
  sistema responde **400**, JSON
  `{"status": "invalido", "mensagem": "requisição inválida"}`, sem
  consultar o banco (guardrail 12). Essa é a única resposta diferente da
  rejeição genérica: depende só do formato do `projeto_id`, nunca do
  token.
- Quando ocorre **qualquer** um dos casos abaixo, sozinho ou combinado
  com outros, o sistema não grava e responde a **rejeição genérica**:
  **409**, JSON `{"status": "rejeitado", "mensagem": "voto já registrado"}`,
  corpo byte a byte idêntico em todos os casos (guardrail 5):
  - voto duplicado (token, projeto), inclusive o perdedor de uma corrida;
  - token ausente, malformado (não é UUID) ou inexistente;
  - token emitido por estação de outra edição;
  - sem cadastro válido;
  - votação fechada (nenhuma edição em votação);
  - projeto inexistente;
  - projeto com status diferente de `publicado`;
  - projeto de outra edição (turma de outra edição).
- As verificações acima e a inserção acontecem na mesma transação
  atômica, depois da trava da edição; a unicidade continua garantida pela
  constraint do banco — o `IntegrityError` da constraint vira a rejeição
  genérica (guardrail 4).
- Quando dois requests simultâneos tentam o mesmo (token, projeto), apenas
  um é gravado (constraint no banco, guardrail 4); o outro recebe a
  rejeição genérica.

### Validação de entrada (guardrail 12)
Feita antes de qualquer consulta de negócio. Tamanhos em caracteres,
depois de remover espaços nas pontas.

| Endpoint | Entrada | Regra | Falha → resposta |
|---|---|---|---|
| `GET /estacao/<id>` | `id` (rota) | conversor `<int:id>` | não casa → 404 (rota inexistente); estação inexistente ou inativa → 404. Antes disso: anônimo → login do admin; logado sem `is_staff` ou sem `votacao.operar_estacao` → 404 |
| `GET /visitantes` | — | sem entrada; query string ignorada; lê só o cookie de cadastro | cadastro válido → redirect para `/votar` |
| `GET /entrar` | `w` | exatamente 1 ocorrência; até 32 caracteres; formato `<estacao>:<timestamp>`, `estacao` = inteiro 1–2147483647 sem sinal nem zero à esquerda, `timestamp` = inteiro Unix em segundos, 10 dígitos | página "QR expirado" (400) |
| `GET /entrar` | `sig` | exatamente 1 ocorrência; 64 caracteres hexadecimais minúsculos (HMAC-SHA256); comparação com `hmac.compare_digest` (G2) | página "QR expirado" (400) |
| `GET /entrar` | cookie do token | UUID canônico (36 caracteres, com hífens); outro valor = cookie ausente | emite token novo |
| `POST /visitantes` | `nome` | obrigatório; 2–120 caracteres; sem caractere das categorias Unicode `Cc` (controle), `Cf` (formatação invisível, ex: U+200B, U+202E, U+FEFF), `Zl` e `Zp` (separadores de linha e parágrafo); ao menos um caractere que não seja espaço no sentido Unicode (NBSP, U+3000 e os demais `Zs` contam como espaço) | 400, formulário com mensagem genérica |
| `POST /visitantes` | `email` | obrigatório; até 254 caracteres; `EmailValidator` do Django | 400, idem |
| `POST /visitantes` | `telefone` | opcional; até 20 caracteres; só dígitos, espaço, `(`, `)`, `-` e um `+` opcional no começo (`^\+?[0-9 ()-]*$`); depois de remover o que não é dígito: 10 ou 11 dígitos (DDD + número), ou 12–13 começando com `55`; gravado só com os dígitos | 400, idem |
| `POST /visitantes` | `consentimento` | obrigatório e marcado (checkbox, `BooleanField(required=True)`) | 400, idem |
| `POST /visitantes` | IP do cliente | no máximo 300 envios por 10 min por IP (`chave_ip(ip_do_cliente(request))`), antes da trava da `Edicao` — fatia F5b | 400, formulário com mensagem genérica, nada gravado |
| `POST /visitantes`, `POST /votos` | token CSRF | padrão do Django | 403 do Django |
| `GET /votar` | cookie do token | UUID canônico; outro valor = sem token | redirect para `/como-votar/` (`vitrine:como_votar`, spec 02) |
| `POST /votos` | `projeto_id` | exatamente 1 ocorrência; só dígitos, 1–10 caracteres, valor 1–2147483647 | 400 JSON `invalido` |
| `POST /votos` | cookie do token | UUID canônico; outro valor = token inexistente | 409 rejeição genérica |
| todas | cookie de cadastro | assinatura válida; `edicao_id` = edição em votação | sem cadastro (ver "Liberação da cédula") |

- Campos de formulário além dos listados são ignorados.
- Mensagens de erro nunca citam o valor recebido, o segredo HMAC nem qual
  regra barrou (G3, G5).

## Correlação visitante × token (B1)
> **Aceita** — decisão do coordenador no PR #18: P1 aceito; P2 aceito com
> o ajuste do 5xx abaixo. Origem: revisão do Codex (B1) — o horário
> truncado não fecha sozinho os caminhos de correlação.

**P1 — id de visitante sem ordem.** `Visitante.id` é `UUIDField`
(`primary_key=True`, `default=uuid.uuid4`, `editable=False`). Sem
sequência no banco, o id não revela a ordem de cadastro, que se aproxima
da ordem de `tokens.criado_em`. O model não declara `Meta.ordering`
por id.

**P2 — log da aplicação sem rastro do visitante.** Nas rotas `/entrar`,
`/visitantes`, `/votar` e `/votos`, a aplicação **não registra nenhuma
linha por request** — nem a linha de 4xx do logger `django.request`
(ex: "Bad Request: /entrar"), nem `django.security` (CSRF). Erros 5xx
dessas rotas são registrados com o **tipo da exceção, a rota e a pilha
de chamadas (arquivo e linha de cada quadro)**, **sem a mensagem da
exceção** — a mensagem é o que vaza (ex: o `IntegrityError` traz os
valores da chave), e sem a pilha não dá para consertar nada no dia do
evento. Também sem variáveis locais dos quadros, sem o objeto `request`,
sem IP, sem cookie, sem query string (`w`, `sig`), sem corpo, sem
user-agent, sem id de request/sessão, sem token, sem nome ou email.
Implementação: filtro `votacao/logs.py` aplicado aos loggers
`django.request`, `django.security`, `django.security.csrf` (pelo nome) e
`votacao`, e também ao handler `console`. Implementado no PR #26 e
ligado em `LOGGING` (`settings.py`) pelo coordenador no PR #27. Filtro de
logger não pega o que propaga dos filhos, daí o `csrf` pelo nome; os
`django.security.<Classe>` do `SuspiciousOperation` não dá para listar, e
o handler os cobre. Fica também no logger porque `assertLogs` troca os
handlers e o filtro só no handler sumiria nos testes.

**Dependência do coordenador — logs da hospedagem (ADR-006).** Critério
na escolha do servidor (até 08/10): plataforma que não permite tirar o
log de acesso das rotas do visitante perde pontos; o `gunicorn` fica sem
log de acesso (padrão dele). O log de
acesso do servidor de aplicação (gunicorn ou equivalente), do proxy e da
plataforma registra método, caminho, IP e horário com segundos, fora do
alcance do código. Precisa ficar desligado ou sem essas rotas, inclusive
o log de erro do proxy. A plataforma também carimba com segundos cada
linha que a aplicação escreve no console — por isso P2 não escreve linha
nos fluxos de sucesso. Retenção curta não basta: enquanto o log existe,
o vínculo existe.

**Risco residual.** Mesmo com P1 e P2, quem tem acesso
ao banco ou a um `pg_dump` vê as linhas de `visitantes` e `tokens` na
ordem física de gravação, e numa hora com poucos cadastros o horário
truncado ainda permite inferência. O controle que resta é o acesso
restrito ao banco e aos dumps (ADR-006). A spec não promete anonimato
absoluto contra quem tem o banco inteiro. As chaves por IP do rate limit
ficam na tabela do `DatabaseCache` até expirarem e serem removidas pela
limpeza do cache; guardam o HMAC do IP (nunca o IP em claro) e não têm
token nem visitante.

**Aceites:**
- [ ] Revisão de schema: `visitantes.id` é UUID com `default=uuid4`; a migration não cria sequência para `visitantes`
- [ ] Teste: dois cadastros seguidos geram ids sem relação de ordem com a ordem de cadastro (não é inteiro; não é UUID v1/v7)
- [ ] Teste com `assertLogs` em nível DEBUG nos loggers `django`, `django.request`, `django.security` e `votacao`, cobrindo o fluxo `/entrar` → `/visitantes` → `/votar` → `/votos` com sucesso e com rejeições (400, 409, CSRF): **nenhum registro** é emitido
- [ ] Teste forçando exceção em `POST /visitantes` e em `GET /entrar` (mensagem da exceção com um valor marcador): o registro de erro tem o tipo da exceção, a rota e a pilha com arquivo e linha; não tem a mensagem da exceção (nem o marcador), variáveis locais nem atributo `request`, e não contém o IP fictício (`203.0.113.7`), o token, o cookie, `w`, `sig`, nome ou email fictícios
- [ ] Revisão de código: nenhum `logger.*` nas views do visitante passa dado de request, token ou visitante
- [ ] Dependência (coordenador, antes do ensaio de 22/10): configuração de log da hospedagem conferida e anexada ao PR de deploy (ADR-006)

## Dados
Alterações de schema com migration versionada (guardrail 16). Models do
app `votacao`, com `db_table` explícito — os nomes de tabela são os que
a spec 04 e o G6 citam:

| Model | Tabela | Campos |
|---|---|---|
| `Estacao` | `estacoes` | id, nome (char 60), ativa (bool), **edicao (FK → `Edicao`, `PROTECT`, obrigatório; não muda depois da primeira emissão)** |
| `Token` | `tokens` | id (uuid, pk), estacao (FK → `Estacao`, `PROTECT`), criado_em. A edição do token é `estacoes.edicao_id` — sem coluna própria de edição |
| `Voto` | `votos` | id, token (FK `PROTECT`), projeto (FK → `Projeto`, `PROTECT`), criado_em, **unique (token_id, projeto_id)** |
| `Visitante` | `visitantes` | id (**UUID — P1**), nome (char 120), email (char 254), telefone (char 13, só dígitos, null), consentimento_em (**truncado para a hora**), **edicao (FK → `Edicao`, `PROTECT`, obrigatório, preenchido com a edição em votação no cadastro)**. **Sem coluna de token, voto ou estação** (guardrail 6). Nenhum outro campo de data/hora |
| `EdicaoVotacao` | — | proxy de `Edicao` (sem tabela), só para as ações de abrir/encerrar no admin |

- **Escreve** na spec 01: só `Edicao.votacao_aberta_em` e
  `Edicao.votacao_encerrada_em`, pelas ações de abrir/encerrar.
- **Lê** da spec 01: `Edicao`; `Turma.edicao`; `Projeto` (título, turma,
  status — só `publicado` entra na cédula e no voto).
- A tabela `config_votacao` não existe mais (spec 01, PR #16).

## Endpoints / telas
| Método | Rota | Entrada | Saída | Erros |
|---|---|---|---|---|
| GET | `/estacao/<int:id>` | sessão de staff com `votacao.operar_estacao` | HTML com QR autoatualizável, `Cache-Control: no-store` | 404 estação inexistente/inativa ou id não inteiro; 302 para `admin:login` (anônimo); 404 (logado sem `is_staff` ou sem `votacao.operar_estacao`) |
| GET | `/visitantes` | cookie de cadastro | formulário de visitante; redirect p/ cédula com cadastro válido | 400 página "QR expirado" se votação fechada |
| GET | `/entrar` | `w`, `sig` (query); cookie do token | 200 página que grava o token no localStorage e redireciona ao formulário (ou à cédula, com cadastro válido) + cookie do token | 400 página "QR expirado" (entrada malformada, assinatura, expiração, estação inativa ou de outra edição, votação fechada, rate limit estourado) |
| POST | `/visitantes` | nome, email, telefone?, consentimento | redirect p/ cédula + cookie de cadastro | 400 formulário com mensagem genérica; 400 página "QR expirado" se votação fechada; 403 CSRF |
| GET | `/votar` | cookie do token, cookie de cadastro | cédula (projetos `publicado` da edição em votação) com estado de votos do token | redirect p/ `/como-votar/` (`vitrine:como_votar`, spec 02) (sem token, malformado, inexistente ou de outra edição); redirect p/ formulário (sem cadastro válido); aviso "Votação encerrada" |
| POST | `/votos` | `projeto_id`; cookies | 201 `registrado` | 400 `invalido` (`projeto_id` malformado); 409 rejeição genérica (todas as demais); 403 CSRF |
| admin | Votação por edição | ações Abrir / Encerrar | mensagem de sucesso | mensagens de recusa acima; 403 não superusuário |
| admin | Estações | nome, edição, ativa | — | `ValidationError` ao mudar edição com tokens; apagar com tokens bloqueado |

## Guardrails aplicáveis
1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16, 17.

- 4: verificação de projeto/edição/token/cadastro e inserção do voto na
  mesma transação, depois da trava da `Edicao`; unicidade
  `(token_id, projeto_id)` no banco; abertura concorrente serializada.
- 5: token ausente, malformado, inexistente ou de outra edição, sem
  cadastro, votação fechada e projeto inexistente, não publicado ou de
  outra edição caem na mesma resposta 409 com corpo idêntico.
- 6: `visitantes.edicao_id` vem da `Edicao`, nunca do token; a liberação
  da cédula não grava vínculo no servidor; horário truncado + P1 + P2
  reduzem a correlação (residual descrito em "Correlação visitante ×
  token (B1)").
- 7: rate limit em `/entrar` em duas camadas — 20 tokens por janela de
  45s por estação e 300 emissões por 10 min por IP; estouro = página "QR
  expirado" idêntica; IP só como HMAC na chave de cache, com expiração.
- 8: `GET /votar` sem token válido redireciona para `/como-votar/`
  (`vitrine:como_votar`, spec 02), nunca mostra a cédula; a página e o
  botão da vitrine são da spec 02.
- 9: `edicao_id` não é dado pessoal; nenhum campo pessoal novo.
- 10: o aceite continua registrado com data e hora (hora cheia), junto ao
  cadastro.
- 11: nenhum dado de visitante em log (P2).
- 12: matriz de validação acima, antes do banco.
- 15: abrir/encerrar e estações só para superusuário no admin; página da
  estação só para staff com `votacao.operar_estacao`.

## Critérios de aceite

**Emissão e janela**
- [ ] QR da estação muda sozinho a cada 45s sem recarregar manualmente
- [ ] URL capturada deixa de emitir token após a expiração da janela
- [ ] Re-scan no mesmo navegador devolve o mesmo token (cookie)
- [ ] Cookie do token com valor que não é UUID (`abc`, UUID sem hífens, 37 caracteres) → token novo emitido, sem erro 500
- [ ] `w` malformado (`abc`, `1:`, `:1700000000`, `01:1700000000`, `-1:1700000000`, 33 caracteres, `w` repetido) e `sig` malformado (63 e 65 caracteres, maiúsculas, não hex, ausente) → mesma página "QR expirado", status 400, corpo idêntico ao da assinatura inválida
- [ ] `/estacao/abc` → 404; estação inativa → 404
- [ ] Com votação encerrada, `/entrar`, `POST /visitantes` e `/votos` recusam
- [ ] `timestamp` em agora − 90s e agora + 5s → aceito; agora − 91s e agora + 6s → página "QR expirado"

**Rate limit** (guardrail 7)
- [ ] 20 tokens na mesma janela da mesma estação passam; o 21º → página "QR expirado"
- [ ] Com a janela de uma estação esgotada, outra estação na mesma hora emite normalmente
- [ ] 300 emissões do mesmo IP (obtido por `ip_do_cliente`) em 10 min passam; a 301ª → página "QR expirado"
- [ ] Resposta do limite estourado: status 400 e corpo byte a byte idêntico ao da assinatura inválida; nenhum token criado
- [ ] Requisições com assinatura inválida não contam no contador da janela (a 21ª válida depois de 50 forjadas ainda é a que estoura)
- [ ] O IP não aparece em log nem em tabela de model; a chave do IP no cache tem expiração de 10 min (revisão de código + teste lendo a chave)
- [ ] Nenhuma chave de cache contém o IP em claro: teste emite com o IP fictício `203.0.113.7` e confere que nenhuma linha da tabela do `DatabaseCache` (chave nem valor) contém `203.0.113.7`; a chave do IP é `rl:entrar:ip:` + `chave_ip("203.0.113.7")`
- [ ] O app `votacao` obtém o IP só por `ip_do_cliente(request)` e monta a chave só com `chave_ip(...)`, de `cadastro/seguranca.py`; nenhuma ocorrência de `REMOTE_ADDR`, `X-Forwarded-For`/`HTTP_X_FORWARDED_FOR` nem `hmac` sobre IP no app (revisão de código + `grep`)
- [ ] Sem `IP_HMAC_SECRET`, a aplicação não sobe; o segredo não é o mesmo valor do `QR_HMAC_SECRET` nem do `RA_HMAC_SECRET` (revisão de código: o rate limit lê só `IP_HMAC_SECRET`)
- [ ] Contadores no `DatabaseCache` (`CACHES["default"]`), sem cache por processo

**Abrir e encerrar**
- [ ] Abrir com outra edição em votação → recusado, nenhuma `Edicao` alterada
- [ ] Teste de concorrência: duas aberturas simultâneas de edições diferentes → no máximo uma edição com `votacao_aberta_em` preenchido e `votacao_encerrada_em` vazio
- [ ] Abrir edição já encerrada → "não pode ser reaberta", campos inalterados
- [ ] Encerrar edição não aberta ou já encerrada → recusado, campos inalterados
- [ ] Abrir e encerrar gravam pela instância com `save()`; nenhum `QuerySet.update()`/`bulk_update` em campo da `Edicao` no app `votacao` (revisão de código)
- [ ] Teste de concorrência: voto que obtém a trava depois do encerramento → 409 e nenhum voto gravado; voto que obteve a trava antes → gravado
- [ ] Staff não superusuário (grupo `digitacao-banca`) não vê as ações e recebe 403 ao chamá-las; anônimo → login

**Estação**
- [ ] Mudar a edição de estação com token emitido → `ValidationError`, edição inalterada; sem token emitido → permitido
- [ ] Apagar estação com token emitido → bloqueado (`ProtectedError`)

**Acesso à página da estação**
- [ ] Anônimo em `/estacao/<id>` de estação ativa → 302 para `admin:login` com `next=/estacao/<id>`; o corpo não contém QR, `w` nem `sig`
- [ ] Anônimo em `/estacao/<id>` de estação inexistente → o mesmo 302 (não revela se a estação existe)
- [ ] Usuário logado sem `is_staff` → 404, corpo igual ao da estação inexistente
- [ ] Staff sem `votacao.operar_estacao` (ex: grupo `digitacao-banca`) → 404, corpo igual ao da estação inexistente e ao do logado sem `is_staff`
- [ ] Usuário com `votacao.operar_estacao` mas sem `is_staff` não loga pelo `admin:login`; com sessão antiga → 404
- [ ] Usuário staff com `is_active = False` não loga; com sessão antiga, recebe o mesmo tratamento do anônimo
- [ ] Staff ativo do grupo "estação" → 200 com o QR; estação inexistente ou inativa → 404
- [ ] A permissão `votacao.operar_estacao` existe (migration do app `votacao`) e não dá acesso a nenhum model no admin
- [ ] A renovação do QR exige a mesma autenticação e permissão (anônimo ou staff sem a permissão não obtém `w`/`sig` por ela)
- [ ] Resposta da estação com `Cache-Control: no-store`

**Formulário de visitante**
- [ ] `GET /visitantes` com votação aberta e sem cadastro válido → 200 com o formulário e o texto do consentimento, com ou sem cookie do token
- [ ] `GET /visitantes` com cookie de cadastro válido → 302 para `/votar`, sem formulário e nenhum registro novo em `visitantes`; cookie de cadastro adulterado ou do ensaio, na votação do evento → 200 com o formulário
- [ ] `GET /visitantes` sem edição em votação → página "QR expirado", 400
- [ ] `GET /visitantes` não lê o cookie do token nem a estação (revisão de código) e não cria registro em sessão nem cache
- [ ] `GET /votar` sem token, com token malformado, inexistente ou de outra edição → redirect para `/como-votar/` (`vitrine:como_votar`, spec 02)

**Visitante**
- [ ] `nome` com 1 e 121 caracteres, ausente ou com caractere de controle → 400; com 2 e 120 → aceito
- [ ] `nome` com U+200B, U+202E, U+FEFF ou U+2028, ou só com 2×NBSP ou 2×U+3000 → 400; NBSP entre letras e acentos → aceito
- [ ] `POST /visitantes` válido com cookie de cadastro válido da edição em votação → 302 para `/votar`, nenhum registro novo, o mesmo cookie (não regravado); conferido dentro da transação com a `Edicao` travada; formulário inválido com cadastro válido → 400 com o formulário
- [ ] (F5b) 300 envios de `POST /visitantes` do mesmo IP em 10 min passam; o 301º → 400 com o formulário e a mensagem genérica, nada gravado, sem travar a `Edicao`; a chave no cache é a de `chave_ip`, sem o IP em claro
- [ ] `email` inválido, ausente ou com 255 caracteres → 400; com 254 válido → aceito
- [ ] `telefone` com 9 dígitos, 14 dígitos, letras, 21 caracteres ou `+` fora do começo (`1+7 99999-9999`) → 400; vazio, `(17) 99999-9999` e `+55 17 99999-9999` → aceitos e gravados só com dígitos
- [ ] Consentimento ausente ou desmarcado → 400, nada gravado, sem cookie de cadastro, `/votar` não libera a cédula
- [ ] `visitantes` não tem nenhuma coluna ligando ao token, voto ou estação (revisão de schema)
- [ ] Visitante cadastrado recebe `edicao_id` da edição em votação; teste com cookie de token de **outra** edição presente no request mostra que o `edicao_id` gravado continua o da edição em votação
- [ ] O código do cadastro de visitante não lê token, cookie do token, localStorage nem estação (revisão de código)
- [ ] Aceite às 19:42:17 de 25/10/2026 em `America/Sao_Paulo` grava `consentimento_em` = 2026-10-25 22:00:00 UTC (19:00:00 em Brasília), com minutos, segundos e microssegundos zerados
- [ ] `visitantes` não tem outro campo de data/hora além de `consentimento_em` (revisão de schema: sem `auto_now`/`auto_now_add`)

**Liberação da cédula**
- [ ] Token recém-emitido, sem cadastro: `GET /votar` → redirect para o formulário; `POST /votos` → 409 genérico, nenhum voto gravado
- [ ] Formulário inválido enviado → `/votar` continua redirecionando para o formulário
- [ ] Cadastro válido → `/votar` mostra a cédula; o cookie de cadastro de dois visitantes da mesma edição tem o mesmo valor
- [ ] Cookie de cadastro adulterado ou do ensaio, na votação do evento → sem cadastro (redirect para o formulário)
- [ ] Re-scan na mesma edição com cadastro válido → cédula direto, nenhum novo registro em `visitantes`
- [ ] Nenhum registro é criado na tabela de sessão do Django nem no cache durante `POST /visitantes` → `GET /votar` → `POST /votos` (teste conta as linhas antes e depois; em `/entrar`, só as chaves do rate limit)

**Cédula e voto**
- [ ] Cédula lista só projetos `publicado` da edição em votação: projeto em `em_revisao` da mesma turma e projeto `publicado` de outra edição não aparecem
- [ ] Voto válido → 201 `{"status": "registrado"}`
- [ ] Segundo voto no mesmo projeto pelo mesmo token → 409 genérico
- [ ] Igualdade da rejeição: voto duplicado, perdedor da corrida, token ausente, token malformado, token inexistente, token de outra edição, sem cadastro, votação fechada, projeto inexistente, projeto não `publicado`, projeto de outra edição, e combinações (ex: votação fechada + token inexistente) → todos com status 409 e corpo byte a byte igual, e nenhum voto gravado
- [ ] `projeto_id` malformado (`abc`, `1.5`, vazio, ausente, `0`, `-1`, `+1`, `2147483648`, 11 dígitos, repetido) → 400 `invalido`, nenhuma query ao banco (`assertNumQueries(0)`; a validação vem antes da trava da edição)
- [ ] Teste de corrida: 2 POSTs simultâneos (mesmo token+projeto) → 1 voto no banco; o outro recebe 409 genérico

**Isolamento por edição** (fixture com a edição do evento e a edição "Ensaio", cada uma com turma, projetos e estação próprios)
- [ ] Token emitido por estação do ensaio não vota em projeto do evento (409 genérico, nenhum voto gravado)
- [ ] Re-scan no evento com cookie de token do ensaio emite token **novo**, ligado a estação do evento; o token do ensaio continua intacto
- [ ] Votos do ensaio não aparecem como votados na cédula do evento (e vice-versa)
- [ ] Visitante cadastrado durante a votação do ensaio fica com `edicao_id` do ensaio; durante a do evento, com o do evento
- [ ] Encerrar o ensaio e abrir o evento não altera nem apaga tokens, votos ou visitantes do ensaio

- [ ] Testes do caminho crítico passando (emissão, rate limit, unicidade, rejeições, liberação da cédula, isolamento)

## Decisões do coordenador incorporadas
- Cédula e voto só com projetos `publicado` — mesmo filtro do ranking da
  spec 04 (PR #14, resposta 7).
- O ensaio é outra edição ("Ensaio 2026/2"), com turmas, projetos e
  estações próprios; nada de reabrir votação ou apagar dados (PR #14,
  resposta 8).
- `Estacao` ganha `edicao_id` e os tokens chegam à edição pela estação;
  `Visitante` ganha `edicao_id` direto, preenchido pela edição em votação,
  nunca pelo token (PR #14, resposta 13).
- `visitantes.consentimento_em` gravado truncado para a hora (PR #14,
  "Ponto para a spec 03"); registro na ADR-003 pelo coordenador no PR da
  importação (PR #18, resposta 4).
- Abertura e encerramento nos campos `Edicao.votacao_aberta_em` e
  `Edicao.votacao_encerrada_em`, preenchidos pela spec 03;
  `votacao_aberta_em` não muda depois de preenchido; a tabela
  `config_votacao` deixa de existir (spec 01, PR #16, commit `e5a594a`).

## Decisões do PR #18
Respostas do coordenador à revisão da spec 03 (decisão do coordenador no
PR #18). Restam só dependências do coordenador, que não impedem
começar: cabeçalho do IP real em `DJANGO_IP_HEADER` e logs da
hospedagem (ADR-006, até 08/10) e texto LGPD final (até 20/10). O
segredo `IP_HMAC_SECRET` já está no `settings.py` e no `.env.example`
(PR #24).

1. **B1 / P1** (id de visitante UUID) — aceito.
2. **B1 / P2** (sem log nas rotas do visitante) — aceito, com
   ajuste: no 5xx, registra tipo da exceção, rota e pilha de chamadas
   (arquivo e linha), sem a mensagem da exceção. Implementado em
   `votacao/logs.py` (PR #26).
3. **Logs da hospedagem e `LOGGING`** — do coordenador. Entra como
   critério na escolha do servidor (ADR-006, até 08/10); `gunicorn` sem
   log de acesso; o filtro P2 foi ligado em `LOGGING` no PR #27.
4. **Uma edição em votação por vez** — confirmado. Ensaio (22/10) e
   evento (29/10) não se sobrepõem.
5. **ADR-003** (horário truncado) — do coordenador, no PR da importação
   (cadastro 2/3), junto com o limite do horário truncado descrito aqui.
6. **QR a cada 45s, tolerância −90s / +5s** — aceito.
7. **Texto LGPD provisório** — "Aceito que o Centro Paula Souza (Fatec e
   Etec Olímpia) use meu nome, e-mail e telefone para enviar comunicações
   sobre eventos e cursos." Texto final da coordenação até 20/10.
8. **Nomes da spec 01** — PRs #16 e #17 na `main` com os nomes usados
   aqui; item encerrado.
9. **Rate limit (guardrail 7)** — duas camadas: 20 tokens por janela de
   45s por estação; 300 emissões por 10 min por IP; IP do cabeçalho da
   ADR-006 (coordenador informa até 08/10), só como chave de cache com
   expiração, com o HMAC do IP e nunca o IP em claro (recomendação do
   coordenador no PR #18; segredo `IP_HMAC_SECRET`); estouro = página
   "QR expirado" 400 idêntica; contadores no `DatabaseCache`.
10. **Trava por voto** — mantida; medir no pré-ensaio de 21/10. Plano B,
    não implementar agora: o voto deixa de travar a `Edicao` e a spec 04
    conta só votos com `criado_em` antes de `votacao_encerrada_em`.

Regra transversal do coordenador (PR #17): campos travados da `Edicao`
só mudam via `save()` ou métodos do model, nunca `QuerySet.update()` —
aplicada em "Abrir e encerrar".

## Decisões do PR #20
Parecer do coordenador sobre o acesso à estação e o IP (decisão do
coordenador no PR #20).

1. **Página da estação** — exige `is_staff` e a permissão
   `votacao.operar_estacao`, dada ao grupo "estação"; logado sem a
   permissão → 404, como sem staff. Ver "Acesso à página da estação".
2. **IP do cliente** — só por `ip_do_cliente(request)` e
   `chave_ip(texto)` de `cadastro/seguranca.py` (PR #25); o cabeçalho é
   `DJANGO_IP_HEADER`, do coordenador. Ver "Rate limit da emissão".
3. **`GET /visitantes` com cadastro válido** — redirect para a cédula.
   Ver "Formulário de visitante".

## Decisões do PR #33
Parecer do coordenador sobre o cadastro do visitante (decisão do
coordenador no PR #33).

1. **Formulário recusado volta preenchido** — de acordo: volta só o que
   o próprio visitante digitou, nada gravado, com `no-store` e escape do
   template; o G11 protege o dado guardado.
2. **Caracteres invisíveis no nome** — o nome recusa as categorias
   Unicode `Cc`, `Cf`, `Zl` e `Zp` e exige ao menos um caractere que não
   seja espaço no sentido Unicode. Ver "Validação de entrada".
3. **`POST /visitantes` com cadastro já válido** — redirect para a
   cédula, sem gravar; conferido depois da validação do formulário e
   dentro da transação, com a `Edicao` travada. Ver "Cadastro do
   visitante".
4. **Rate limit no `POST /visitantes`** — 300 por 10 min por IP, como o
   `/entrar`, com `chave_ip(ip_do_cliente(request))`, antes da trava;
   estouro → 400 com o formulário e a mensagem genérica, nada gravado.
   Implementado na fatia F5b, depois da F4, que cria a infraestrutura do
   rate limit. Ver "Cadastro do visitante".
