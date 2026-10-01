# Vitrine CPS — Contexto do projeto

## O que é
Plataforma web para a mostra semestral de projetos da FATEC Olímpia e da Etec (cursos de DSM, GTUR e outros do Centro Paula Souza). Os alunos cadastram seus projetos, cada projeto ganha uma página pública de divulgação, e no dia do evento o público presente vota nos seus favoritos. O sistema é recorrente: será usado em todas as edições semestrais daqui em diante.

## Objetivos
1. Dar visibilidade aos projetos dos alunos por meio de páginas públicas compartilháveis.
2. Atrair público para o evento presencial na FATEC (o link divulga, mas o voto é presencial).
3. Garantir votação justa, com voto único por pessoa por projeto, sem cadastro do eleitor.
4. Captar contatos dos visitantes (nome, email, telefone) para comunicações futuras da coordenação — sem vincular ao voto.
5. Gerar relatório de resultados por categoria ao fim da votação.

## Atores
- **Administrador**: cadastra edições (semestres), turmas/categorias e abre/encerra a votação.
- **Aluno (grupo)**: cadastra o projeto do seu grupo dentro de uma turma — título, descrição, informações do projeto, links externos (repositório, vídeo, redes) e imagens.
- **Banca (jurados)**: avaliam os projetos com nota 0–10 por critério, com login próprio. Peso maior que o do público (ADR-007).
- **Público**: acessa as páginas de vitrine pela internet; no dia do evento, vota presencialmente.

## Módulos

### 1. Cadastro
- Edições (semestres) → turmas/categorias → projetos (pertencem a uma turma e a uma edição).
- Cada projeto: título, descrição, equipe, links externos, galeria de imagens.

### 2. Vitrine pública
- Cada projeto tem um link público permanente (ex: `/projeto/nome-do-projeto`) com página de apresentação.
- O link circula livremente (WhatsApp, redes sociais) para divulgar o projeto e o evento.
- A página convida para o evento presencial; **o link público não vota**.

### 3. Votação presencial (dia D)
- **Credenciamento por QR dinâmico em múltiplas estações**: computadores/tablets espalhados pelo evento exibem a página `/estacao` em tela cheia, com QR que rotaciona a cada 30–60s. Cada scan cria um token único (UUID) no servidor — nada é pré-gerado.
- **Estações identificadas**: o id da estação entra na janela assinada (`w=<estacao>:<timestamp>`). O rate limit por janela vale por estação, e o relatório mostra emissões por estação (detecção de anomalia localizada).
- Estações ficam onde há staff/monitores por perto (recepção de blocos), nunca QR solto sem supervisão — o backstop de unicidade é humano.
- **URL do QR assinada**: o QR aponta para `/entrar?w=<estacao>:<janela>&sig=<HMAC>`; o servidor valida assinatura e expiração da janela. Sem isso a rotação seria cosmética — a URL capturada emitiria tokens remotamente para sempre.
- **Idempotência por cookie httpOnly**: no primeiro `/entrar`, o token é gravado em cookie httpOnly (além do localStorage); re-scans do mesmo navegador devolvem o mesmo token em vez de criar outro.
- **Rate limit em duas camadas na emissão**: (a) por IP, generoso — Wi-Fi do evento sai por um único NAT, limite agressivo bloquearia eleitores legítimos; (b) por janela de QR/estação — se passam ~5 pessoas por rotação, uma janela com 30 emissões é anomalia e é cortada.
- **Cadastro do visitante pós-scan**: emitido o token, a primeira tela no celular do eleitor é o formulário de contato — ele preenche andando, no próprio aparelho, sem segurar fila na estação. Nome e email obrigatórios para liberar a cédula; telefone opcional. Sem CPF (sensível demais para a finalidade).
- **Desacoplamento voto × identidade**: os dados do visitante gravam na tabela `visitantes` **sem chave para o token**. A coordenação recebe a lista de contatos; os votos permanecem anônimos.
- **LGPD**: checkbox de consentimento com finalidade declarada ("aceito receber comunicações da FATEC Olímpia").
- O eleitor pode circular pelo evento e votar quando quiser, dentro da janela de votação.
- **Cédula**: lista todos os projetos; voto **livre** — o eleitor vota em quantos projetos quiser. Regra de unicidade: **1 token = no máximo 1 voto por projeto** (registra-se quais projetos cada token já votou).
- Voto duplicado no mesmo projeto, token inexistente ou fora da janela → rejeitado ("voto já registrado"), sem revelar informação.
- Registro do voto em transação atômica para evitar corrida entre requests simultâneos.
- Geolocalização foi avaliada e descartada (não garante unicidade e é falsificável).

#### Limitação conhecida (decisão consciente)
Pessoa presente com múltiplos aparelhos consegue múltiplos tokens. Não há solução técnica sem identificar o eleitor (cadastro/CPF), descartado por fricção. O backstop é o controle físico nas estações (staff acompanhando os scans). Camadas técnicas acima elevam o esforço; a camada humana fecha o resto — proporcional ao risco de uma mostra acadêmica.

### 4. Resultados
- Ao encerrar a votação, o sistema gera relatório de resultados **por categoria/turma** (ranking, total de votos, participação).
- Relatório operacional: emissões de token por estação, cadastros de visitantes coletados.

## Decisões de arquitetura já tomadas
Ver `docs/02-decisoes.md` (registro de decisões). Resumo:
- Divulgação e votação são fluxos separados: o link público converte em presença física; só o token obtido na entrada permite votar.
- Tokens gerados sob demanda no scan (rota `/entrar`), não pré-impressos.
- Múltiplas estações de credenciamento, cada uma com id próprio na assinatura do QR.
- Token válido até o fim da janela de votação do evento (horas); o que expira rápido é a assinatura do QR da estação.
- Voto livre (sem limite de projetos por eleitor), com máximo de 1 voto por projeto por token.
- Cadastro de visitante obrigatório (nome + email; telefone opcional) para liberar a cédula, preenchido no celular do eleitor — nunca na estação.
- Dados de visitantes desacoplados do token: voto anônimo, lead para a coordenação.
- Modelo de dados com edições desde o início, para reuso semestral sem migração.

## Pontos em aberto
- Stack de implementação (backend, banco, hospedagem) — registrar como ADR-002 quando decidido.
- Quem administra: alunos de DSM, professores, ou ambos?
- Identidade visual da marca Vitrine CPS.
- Texto final do consentimento LGPD (validar com a coordenação).
