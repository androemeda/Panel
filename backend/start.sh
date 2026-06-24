#!/usr/bin/env bash
# Backend startup: creates the venv + installs deps on first run, then launches the API.
set -euo pipefail

cd "$(dirname "$0")"

PORT="${PORT:-8000}"
VENV=".venv"
PY="$VENV/bin/python"

# 1. Virtualenv
if [ ! -d "$VENV" ]; then
  echo "[backend] creating virtualenv ($VENV)..."
  python3 -m venv "$VENV"
fi

# 2. Dependencies (re-install when requirements.txt is newer than the stamp)
STAMP="$VENV/.deps-installed"
if [ ! -f "$STAMP" ] || [ requirements.txt -nt "$STAMP" ]; then
  echo "[backend] installing dependencies..."
  "$PY" -m pip install --upgrade pip >/dev/null
  "$PY" -m pip install -r requirements.txt
  touch "$STAMP"
fi

# 3. Environment file
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "[backend] created .env from .env.example — fill in your API keys before using LLM/Pinecone features."
  else
    echo "[backend] WARNING: no .env or .env.example found."
  fi
fi

# 4. Run
echo "[backend] starting uvicorn on http://localhost:$PORT (reload)..."
exec "$PY" -m uvicorn app.main:app --reload --port "$PORT"
