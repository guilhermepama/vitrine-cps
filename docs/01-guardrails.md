# Guardrails — regras inegociáveis

Qualquer agente de IA ou pessoa que gerar código neste repositório deve
respeitar estas regras. **PR que viola um guardrail não é mergeado**, mesmo
funcionando. Em caso de conflito entre uma spec e este arquivo, este arquivo
vence — e o conflito deve ser reportado ao coordenador.

## Segurança da votação

1. **Nenhum endpoint além de `/entrar` emite token.** Token é UUID gerado
   no servidor; nunca aceitar token vindo do cliente para criação.
2. **`/entrar` só emite com janela assinada válida** (`w=<estacao>:<timestamp>`
   + `sig=HMAC`). Validar assinatura E expiração no servidor. Comparação da
   assinatura em tempo constante (`timingSafeEqual` ou equivalente).
3. **O segredo HMAC vive em variável de ambiente.** Nunca em código, nunca
   em log, nunca em resposta de erro.
4. **Registro de voto é transação atômica** com constraint de unicidade
   `(token_id, projeto_id)` no banco. A regra de unicidade mora no banco,
   não só no código da aplicação.
5. **Rejeição silenciosa**: voto duplicado, token inexistente, janela
   expirada → mesma resposta genérica ("voto já registrado"). Nunca revelar
   qual regra barrou, nem se um token existe.
6. **Tabela `visitantes` não tem FK nem coluna que ligue ao token/voto.**
   Qualquer código que crie esse vínculo é rejeitado — quebra o anonimato
   do voto, que é requisito.
7. **Rate limit na emissão em duas camadas** (por IP generoso + por janela
   de estação). Não remover "para testar" e esquecer.
8. **A página pública de vitrine não contém nenhum caminho para votar.**
   Botão "votar" ali leva à explicação do voto presencial, nunca à cédula.

## Dados pessoais (LGPD)

9. Coletar **somente** nome, email, telefone (opcional) e consentimento.
   Nunca CPF, RG ou data de nascimento — nem "já que estamos coletando".
10. Checkbox de consentimento com finalidade explícita; registrar
    data/hora do aceite junto ao cadastro.
11. Dados de visitantes nunca aparecem em log, em página pública ou em
    endpoint sem autenticação de admin.

## Qualidade de código

12. **Validar entrada em todo endpoint** (tipos, tamanhos, formatos) antes
    de tocar no banco. Erros de validação retornam 400 com mensagem
    genérica.
13. Queries sempre parametrizadas — string interpolada em SQL é rejeição
    automática do PR.
14. Upload de imagens: validar tipo e tamanho no servidor; nomes de arquivo
    gerados pelo servidor, nunca o nome original do upload.
15. Autenticação de admin em toda rota administrativa (abrir/encerrar
    votação, relatórios, exportar visitantes).
16. Migrations versionadas no repositório — nenhuma alteração manual de
    schema em produção.
17. Todo módulo entrega junto os testes do seu caminho crítico (no mínimo:
    emissão de token, unicidade de voto, rejeições).

## Processo

18. Nenhum merge em `main` sem PR aprovado pelo coordenador (humano — a IA
    gera, humano revisa). PRs do próprio coordenador são aprovados pelo
    Renan Croffi antes do merge (ADR-010) — por necessidade, entram sem
    essa aprovação, com o motivo no PR —, e nunca sem PR e sem os checks
    do CI verdes (ADR-005).
19. Código gerado por IA é responsabilidade de quem commitou. "A IA que
    fez" não existe como justificativa.
20. Mudança nestes guardrails: só o coordenador, via PR neste arquivo, com
    registro em `docs/02-decisoes.md`.
