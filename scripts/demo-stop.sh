#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_DIR="$PROJECT_ROOT/.demo-pids"

echo "=== RCA Agent Demo — Stopping ==="

stopped=0

if [ -f "$PID_DIR/frontend.pid" ]; then
    PID=$(cat "$PID_DIR/frontend.pid")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null
        # Also kill any child vite processes
        pkill -P "$PID" 2>/dev/null || true
        echo "  Frontend stopped (PID $PID)"
        stopped=$((stopped + 1))
    fi
    rm -f "$PID_DIR/frontend.pid"
fi

if [ -f "$PID_DIR/backend.pid" ]; then
    PID=$(cat "$PID_DIR/backend.pid")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null
        echo "  Backend stopped (PID $PID)"
        stopped=$((stopped + 1))
    fi
    rm -f "$PID_DIR/backend.pid"
fi

# Clean up any orphaned uvicorn/vite on these ports
lsof -ti:8080 2>/dev/null | xargs kill 2>/dev/null || true
lsof -ti:5173 2>/dev/null | xargs kill 2>/dev/null || true

if [ $stopped -eq 0 ]; then
    echo "  Nothing was running."
else
    echo ""
    echo "  Demo stopped. Logs in .demo-pids/*.log"
fi
