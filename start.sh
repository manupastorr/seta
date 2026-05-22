#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

if [[ ! -x "$PY" ]]; then
  echo "Creating Python venv..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r "$ROOT/requirements.txt"
fi

cd "$ROOT"
echo "Scanning library (cached analysis reused when possible)..."
"$PY" scan_library.py "$@"

echo "Starting graph server..."
exec "$PY" server.py
