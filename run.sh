#!/usr/bin/env bash
# Start the Flask development server.
#
# Configuration comes from .env (see .env.example); the app loads it itself.
# Extra arguments are passed to `flask run`, e.g. ./run.sh --port 8010
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

exec flask --app wsgi run --debug "$@"
