#!/usr/bin/env bash
# Launch backend + frontend together. Ctrl-C stops both.
set -euo pipefail

cd "$(dirname "$0")"

cleanup() {
  echo
  echo "[dev] shutting down..."
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

./backend/start.sh &
./frontend/start.sh &

wait
