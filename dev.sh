#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cleanup() {
    echo "Stopping backend and frontend..."
    kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null
}
trap cleanup EXIT INT TERM

(
    cd "$ROOT_DIR/backend/agent"
    ../myenv/bin/python3 -m uvicorn main:app --reload --port 8000
) &
BACKEND_PID=$!

(
    cd "$ROOT_DIR/frontend/serverctl"
    npm run dev
) &
FRONTEND_PID=$!

wait "$BACKEND_PID" "$FRONTEND_PID"