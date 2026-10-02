# Spec — Cadastro (edições, turmas, projetos)

> Stub — completar usando `specs/_template.md` antes de implementar.
> Ver `specs/03-credenciamento-votacao.md` como exemplo do nível de detalhe esperado.

- **Responsável**: Guilherme (@guilhermepama)
- **Status**: rascunho
- **Depende de**: ADR-002 (stack), ADR-009 (cadastro pelo grupo)

## Objetivo
Modelo de dados base e administração do cadastro: edições, cursos, turmas
e projetos. Os projetos nascem da lista das coordenações e são preenchidos
pelos próprios grupos (ADR-009); a equipe importa e aprova.

## Escopo (decidido — detalhar)
- Edição, Curso (estável) e Turma (por edição; período semestre **ou** ano).
- Projeto: turma, título, descrição, equipe, links externos, imagens (R2).
  **Slug gerado uma vez e imutável** — o link público não pode quebrar.
- Status do projeto: `pre_cadastrado` → `em_revisao` → `publicado`, ou
  `ajustes` (volta ao grupo).
- Representante: nome + **HMAC-SHA256 do RA** (segredo em variável de
  ambiente). RA em claro nunca é gravado nem logado.
- Token de edição: aleatório, guardado como hash; revogável; regerado
  pelo admin em 1 clique (o anterior deixa de valer).
- Importação da lista das coordenações (planilha modelo em
  `docs/modelos/lista-projetos-vitrine-cps.xlsx`, exportada para CSV)
  por comando de gerenciamento: idempotente, relatório de erros por linha.
- Admin: filtros por status/turma, ação em lote "publicar" e "devolver
  para ajustes", regerar link de edição, prazo de edição por edição.

## Fora de escopo
- Telas do grupo (reivindicar por RA, editar) — spec 02.
- Login de aluno, envio de e-mail.

## Guardrails aplicáveis
3 (por analogia: segredo do HMAC do RA), 12, 13, 14, 15, 16, 17.

## Critérios de aceite
- [ ] (a detalhar)
