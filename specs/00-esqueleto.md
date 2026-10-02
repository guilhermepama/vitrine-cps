# Spec — Esqueleto do projeto Django

- **Responsável**: Guilherme (@guilhermepama)
- **Status**: em implementação
- **Depende de**: ADR-002 (stack), ADR-006 (banco Neon, imagens R2)

## Objetivo
Projeto Django vazio, configurado e testado, para que cada frente comece a
trabalhar no próprio app sem tocar em arquivo de outra pessoa.

## Escopo
- `requirements.txt` com a lista fechada da ADR-002, versões fixas.
- Projeto `config/` (settings, urls, wsgi). Tudo que muda entre ambientes vem
  de variável de ambiente; `.env` lido só no desenvolvimento local.
- Os cinco apps das frentes já criados e registrados (`cadastro`, `vitrine`,
  `votacao`, `banca`, `resultados`), vazios. `vitrine` e `votacao` já têm
  `urls.py` incluído na raiz.
- Banco obrigatoriamente PostgreSQL: a aplicação não sobe com outro banco.
- Cache no banco (compartilhado entre workers) — base do rate limit (G7).
- Arquivos estáticos pelo whitenoise; configuração de segurança para rodar
  atrás do HTTPS da plataforma.
- Rota `GET /saude/`: 200 "ok" se o banco responde, 503 caso contrário.
- pytest + pytest-django; testes da fundação.
- Postgres local opcional por `docker-compose.yml`; instruções no README.

## Fora de escopo
- Models de qualquer frente (spec 01 em diante).
- Configuração do R2 (entra com os models do cadastro, junto do primeiro
  campo de imagem).
- Identidade visual, template base, arquivos de deploy específicos de uma
  plataforma (servidor ainda em aberto — ADR-006).

## Comportamento esperado
- Sem `DJANGO_SECRET_KEY` ou sem `DATABASE_URL`, a aplicação não sobe e diz
  qual variável falta.
- `DATABASE_URL` de outro banco que não Postgres: a aplicação não sobe.
- `DJANGO_DEBUG` desligado por padrão. Desligado, cookies só por HTTPS.
- `/saude/` não revela detalhe de erro; só aceita GET.

## Dados
Nenhuma tabela própria. Tabela de cache `cache_django`
(`python manage.py createcachetable`, sem migration).

## Guardrails aplicáveis
3 (segredos só em variável de ambiente), 4 (Postgres em teste e produção),
7 (cache compartilhado para o rate limit), 11 (logs), 15 (admin com login),
16 (migrations em dia no CI), 17 (testes).

## Critérios de aceite
- [x] CI verde: `makemigrations --check` sem mudanças e `pytest` passando
- [x] `/saude/` responde 200 com banco no ar
- [x] `/admin/` redireciona para o login
- [x] Aplicação recusa SQLite e recusa subir sem `DJANGO_SECRET_KEY`
- [x] Cache é o do banco e funciona nos testes
- [x] Cada frente tem seu app criado e registrado

## Perguntas em aberto
- Servidor (ADR-006, até 08/10): define o comando de start e o arquivo de
  deploy. O esqueleto já roda com `gunicorn config.wsgi`.
