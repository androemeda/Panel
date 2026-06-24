#!/usr/bin/env bash
# Frontend startup: installs node deps on first run, then launches the Vite dev server.
set -euo pipefail

cd "$(dirname "$0")"

# Install deps when node_modules is missing or package.json is newer.
if [ ! -d node_modules ] || [ package.json -nt node_modules ]; then
  echo "[frontend] installing dependencies..."
  npm install
fi

echo "[frontend] starting Vite dev server on http://localhost:5173 ..."
exec npm run dev
