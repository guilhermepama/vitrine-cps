# Spec — Avaliação da banca

> Stub — completar usando `specs/_template.md` antes de implementar.
> Regras de negócio já decididas na ADR-007.

- **Responsável**: Guilherme (@guilhermepama)
- **Status**: rascunho
- **Depende de**: ADR-002, ADR-007, ADR-008, spec 01 (projetos e turmas)

## Objetivo
Registrar as notas 0–10, por critério, que cada jurado deu aos projetos
da edição. Nesta edição os jurados avaliam em **ficha impressa** e a
equipe digita as notas no admin (ADR-008).

## Escopo (já decidido — detalhar)
- Critérios cadastrados por edição no admin (nome, ordem).
- Jurado = registro cadastrado no admin (nome, edição) — **sem login**.
- Ficha impressa gerada a partir dos critérios e projetos da edição
  (pode ser uma página para imprimir; o jurado assina a ficha).
- Lançamento das notas no admin **durante o evento**, por usuário do grupo
  "digitacao-banca": só cria/edita avaliações, sem acesso a votos,
  visitantes ou configurações. Registro de quem digitou e quando.
- Conferência por outra pessoa (coordenador): amostra das notas contra as
  fichas antes de publicar o resultado. Quem digita não confere.
- Uma avaliação por (jurado, projeto, critério) — constraint no banco.
- Fichas em papel guardadas como trilha de auditoria.

## Fora de escopo
- Login de jurado e tela de avaliação no celular (próxima edição).
- Cálculo da nota final (spec 04).
- Qualquer vínculo com tokens ou votos do público.

## Guardrails aplicáveis
12, 13, 15, 16, 17.

## Critérios de aceite
- [ ] (a detalhar)
