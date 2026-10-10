# Produção do Vitrine CPS no VPS com Coolify (ADR-006).
# Build: Coolify usa este arquivo (build pack "Dockerfile").
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# curl para o healthcheck do Coolify (a imagem slim não traz curl nem wget;
# sem ele o container nunca fica "healthy" e o Traefik não roteia).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# collectstatic no build (whitenoise, manifest). Os valores abaixo existem só
# porque o settings exige as variáveis para importar; nada conecta em banco
# nem sobe servidor aqui — DJANGO_DEBUG=1 vale só para esta linha.
RUN DJANGO_DEBUG=1 \
    DJANGO_SECRET_KEY=build \
    RA_HMAC_SECRET=build \
    QR_HMAC_SECRET=build \
    IP_HMAC_SECRET=build \
    DATABASE_URL=postgres://build:build@localhost:5432/build \
    python manage.py collectstatic --noinput

EXPOSE 8000

# Migra, garante a tabela do cache (rate limit, guardrail 7) e sobe o gunicorn.
CMD ["sh", "docker/start.sh"]
