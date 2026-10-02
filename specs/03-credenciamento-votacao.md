# Spec — Credenciamento e votação (dia D)

> Spec de referência: usa o template completo para servir de padrão às demais.

- **Responsável**: Renan (@ReCroffi)
- **Status**: pronta para implementar (ADR-002 aceita: Python + Django)
- **Depende de**: ADR-001, ADR-003, spec 01 (modelo de edições/projetos)

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
  token) e libera a cédula.
- Cédula `/votar`: lista projetos da edição ativa agrupados por categoria;
  botão de voto por projeto; projetos já votados pelo token aparecem
  marcados e desabilitados.
- Rota `POST /votos`: registra voto (token, projeto) em transação atômica.
- Janela de votação: admin abre/encerra; fora dela, `/entrar` e `/votos`
  recusam.

## Fora de escopo
- Cadastro de projetos e edições (spec 01).
- Página pública de vitrine (spec 02).
- Relatórios (spec 04).
- Painel do admin além de abrir/encerrar votação.

## Comportamento esperado
- Quando o visitante escaneia o QR dentro da janela de rotação, o sistema
  emite token e redireciona ao formulário.
- Quando o mesmo navegador acessa `/entrar` de novo (cookie presente), o
  sistema devolve o MESMO token — não cria outro.
- Quando a assinatura é inválida ou a janela expirou, o sistema responde
  com página genérica "QR expirado — escaneie novamente na estação".
- Quando o visitante envia o formulário válido, o sistema grava o cadastro
  e exibe a cédula.
- Quando o visitante vota num projeto ainda não votado por aquele token, o
  sistema registra e confirma.
- Quando o voto é duplicado, o token não existe ou a votação está fechada,
  o sistema responde a MESMA mensagem: "voto já registrado" (guardrail 5).
- Quando dois requests simultâneos tentam o mesmo (token, projeto), apenas
  um é gravado (constraint no banco, guardrail 4).

## Dados
- `tokens`: id (uuid, pk), estacao_id, criado_em.
- `votos`: id, token_id (fk), projeto_id (fk), criado_em,
  **unique (token_id, projeto_id)**.
- `visitantes`: id, nome, email, telefone (null), consentimento_em.
  **Sem coluna de token** (guardrail 6).
- `estacoes`: id, nome, ativa.
- `config_votacao`: edicao_id, aberta_em, encerrada_em.

## Endpoints / telas
| Método | Rota | Entrada | Saída | Erros |
|---|---|---|---|---|
| GET | `/estacao/<id>` | — | HTML com QR autoatualizável | 404 estação inexistente/inativa |
| GET | `/entrar` | `w`, `sig` (query) | redirect p/ formulário + cookie token | página "QR expirado" |
| POST | `/visitantes` | nome, email, telefone?, consentimento | redirect p/ cédula | 400 validação |
| GET | `/votar` | cookie/localStorage token | cédula com estado de votos do token | redirect p/ instrução se sem token |
| POST | `/votos` | projeto_id | confirmação | "voto já registrado" (genérico) |

## Guardrails aplicáveis
1, 2, 3, 4, 5, 6, 7, 9, 10, 12, 13.

## Critérios de aceite
- [ ] QR da estação muda sozinho a cada 45s sem recarregar manualmente
- [ ] URL capturada deixa de emitir token após a expiração da janela
- [ ] Re-scan no mesmo navegador devolve o mesmo token (cookie)
- [ ] Formulário sem nome/email ou sem consentimento não libera cédula
- [ ] `visitantes` não tem nenhuma coluna ligando ao token (revisão de schema)
- [ ] Segundo voto no mesmo projeto pelo mesmo token é recusado com mensagem genérica
- [ ] Teste de corrida: 2 POSTs simultâneos (mesmo token+projeto) → 1 voto no banco
- [ ] Com votação encerrada, `/entrar` e `/votos` recusam
- [ ] Testes do caminho crítico passando

## Perguntas em aberto
- Intervalo exato de rotação (45s é proposta) e tolerância de relógio.
- Texto final do consentimento LGPD (coordenação).
