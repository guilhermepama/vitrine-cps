# Spec — Vitrine pública e área do grupo

> Stub — completar usando `specs/_template.md` antes de implementar.
> Ver `specs/03-credenciamento-votacao.md` como exemplo do nível de detalhe esperado.

- **Responsável**: Cleiton (@gustimmolp)
- **Status**: rascunho
- **Depende de**: ADR-002 (stack), ADR-009, spec 01 (models)

## Objetivo
Página pública permanente por projeto (/projeto/<slug>) para divulgação;
convida ao evento presencial e NÃO contém caminho de voto (guardrail 8).
E a área onde o representante do grupo preenche e edita o projeto (ADR-009).

## Escopo (decidido — detalhar)
### Vitrine
- `/projeto/<slug>`: só projetos `publicado`; template único para todos.
- Meta tags Open Graph (título, descrição, imagem) — a prévia no WhatsApp
  é o canal de divulgação.
- Convite para o evento de 29/10; nenhum caminho para votar (G8).
- Equipe: só primeiro nome; sem fotos de pessoas (pendente de decisão da
  coordenação sobre alunos menores da Etec).

### Área do grupo
- Reivindicação: representante informa o RA; se bate com um projeto
  `pre_cadastrado` ainda não reivindicado, o sistema mostra **uma única
  vez** o link de edição, com instrução para guardá-lo.
- RA inexistente ou já reivindicado → **mesma resposta genérica**; rate
  limit na verificação (RAs são sequenciais e enumeráveis).
- Edição via link: formulário com título, descrição, equipe, links e
  imagens; salvar coloca o projeto `em_revisao`. Após o prazo de edição,
  só leitura.
- Upload: tipo e tamanho validados no servidor, nome gerado pelo servidor,
  limite de quantidade (G14).

## Fora de escopo
- Login de aluno, envio do link por e-mail.
- Aprovação e regeração de link (admin — spec 01).

## Guardrails aplicáveis
8, 12, 13, 14, 17.

## Critérios de aceite
- [ ] (a detalhar)
