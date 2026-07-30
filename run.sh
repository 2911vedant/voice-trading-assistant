#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

lsof -ti:5004 | xargs kill -9 2>/dev/null || true
lsof -ti:8080 | xargs kill -9 2>/dev/null || true

cleanup() {
  echo ""
  echo "Stopping backend and frontend..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  echo "Stopped."
  exit 0
}
trap cleanup INT TERM

cd "$BACKEND_DIR"
source venv/bin/activate
export $(grep -v '^#' .env | xargs)

echo "Starting backend on http://localhost:5004 ..."
python app.py &
BACKEND_PID=$!

cd "$FRONTEND_DIR"
echo "Starting frontend on http://localhost:8080 ..."
python3 -m http.server 8080 &
FRONTEND_PID=$!

echo ""
echo "Both running. Open http://localhost:8080 in your browser."
echo "Press Ctrl+C to stop both."

wait "$BACKEND_PID" "$FRONTEND_PID"
