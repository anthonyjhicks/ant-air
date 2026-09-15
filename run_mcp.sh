#!/usr/bin/env bash
# Launch the Ant Air MCP server over stdio for Claude Code / other MCP clients.
# Configuration (DATABASE_URL, API keys) comes from .env; the app loads it itself.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=.venv/bin/python
if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

exec "$PYTHON" -m app.mcp_server
