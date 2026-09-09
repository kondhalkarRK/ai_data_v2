#!/usr/bin/env bash
# Starts the API and the frontend together for local development.
#
# Ctrl+C stops both: the trap kills the API's process group so no orphaned uvicorn is
# left holding port 8000.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

if [[ ! -f .env ]]; then
  echo "No .env found. Copy .env.example to .env and set JWT_SECRET_KEY first." >&2
  exit 1
fi

python_bin="apps/api/.venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  echo "No API virtualenv. Run: cd apps/api && python -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 1
fi

api_pid=""
cleanup() {
  if [[ -n "$api_pid" ]] && kill -0 "$api_pid" 2>/dev/null; then
    echo "Stopping API ..."
    kill "$api_pid" 2>/dev/null || true
    wait "$api_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "Starting API on http://localhost:8000 ..."
(cd apps/api && .venv/bin/python -m uvicorn app.main:app --reload --port 8000) &
api_pid=$!

# Wait for liveness rather than sleeping a fixed amount.
for _ in $(seq 1 40); do
  sleep 0.5
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$api_pid" 2>/dev/null; then
    echo "The API exited during startup. Check the output above." >&2
    exit 1
  fi
done

echo "Starting frontend on http://localhost:3000 ..."
npm run dev
