#!/bin/sh
# Start de produção (ADR-006). Uma instância só: migrate aqui é seguro.
set -e

python manage.py migrate --noinput
# Cache compartilhado entre workers (ver CACHES no settings). Idempotente.
python manage.py createcachetable

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${WEB_CONCURRENCY:-3}" \
  --error-logfile -
