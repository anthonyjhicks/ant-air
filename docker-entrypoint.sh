#!/bin/sh
# Container entrypoint: apply migrations, then run the requested process.
#
#   gunicorn (default)  serve the web app on :8000
#   anything else       run as given, e.g. `python -m app.mcp_server`
set -e

if [ "${AUTO_MIGRATE:-true}" = "true" ] && [ "${1:-gunicorn}" = "gunicorn" ]; then
  echo "Applying database migrations..."
  flask --app wsgi db upgrade
fi

if [ "${1:-gunicorn}" = "gunicorn" ]; then
  shift 2>/dev/null || true
  exec gunicorn \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${GUNICORN_WORKERS:-2}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --worker-class gthread \
    --worker-tmp-dir /dev/shm \
    --graceful-timeout 30 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    wsgi:app "$@"
fi

exec "$@"
