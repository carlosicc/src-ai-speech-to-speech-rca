#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_DIR="$PROJECT_ROOT/.demo-pids"

mkdir -p "$PID_DIR"

# Check if already running
if [ -f "$PID_DIR/backend.pid" ] && kill -0 "$(cat "$PID_DIR/backend.pid")" 2>/dev/null; then
    echo "Demo already running. Use scripts/demo-stop.sh first."
    exit 1
fi

# Resolve AWS credentials for the Smithy SDK (needs env vars, not ~/.aws/credentials)
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-$(aws configure get aws_access_key_id 2>/dev/null)}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-$(aws configure get aws_secret_access_key 2>/dev/null)}"
AWS_SESSION_TOKEN_VAL="$(aws configure get aws_session_token 2>/dev/null || true)"
if [ -n "$AWS_SESSION_TOKEN_VAL" ]; then
    export AWS_SESSION_TOKEN="$AWS_SESSION_TOKEN_VAL"
fi

if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "ERROR: Could not resolve AWS credentials."
    echo "       Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, or configure ~/.aws/credentials."
    exit 1
fi

echo "=== RCA Agent Demo — Starting ==="
echo ""

# --- Backend ---
echo "[1/2] Starting backend (FastAPI + Nova Sonic)..."
cd "$PROJECT_ROOT/src_backend"
NOVA_SONIC_REGION="${NOVA_SONIC_REGION:-us-east-1}" \
NOVA_SONIC_MODEL_ID="${NOVA_SONIC_MODEL_ID:-amazon.nova-sonic-v1:0}" \
VOICE_PASSPHRASE="${VOICE_PASSPHRASE:-REDACTED_PASSPHRASE}" \
VOICE_SESSION_TIMEOUT="${VOICE_SESSION_TIMEOUT:-90}" \
DEFAULT_VOICE_MODE="${DEFAULT_VOICE_MODE:-mode_c}" \
INCIDENT_LOOP_INTERVAL="${INCIDENT_LOOP_INTERVAL:-180}" \
BEDROCK_REGION="${BEDROCK_REGION:-eu-west-1}" \
"$PROJECT_ROOT/.venv/bin/python" -m uvicorn main:app --port 8080 \
    > "$PID_DIR/backend.log" 2>&1 &
echo $! > "$PID_DIR/backend.pid"
echo "       PID $(cat "$PID_DIR/backend.pid") — logs: .demo-pids/backend.log"

# Wait for backend to be ready
for i in $(seq 1 10); do
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

if ! curl -s http://localhost:8080/health > /dev/null 2>&1; then
    echo "ERROR: Backend failed to start. Check .demo-pids/backend.log"
    cat "$PID_DIR/backend.log"
    exit 1
fi
echo "       Backend healthy ✓"

# --- Frontend ---
echo "[2/2] Starting frontend (Vite dev server)..."
cd "$PROJECT_ROOT/src_frontend/app"
VITE_WS_URL="ws://localhost:8080/ws" npx vite --port 5173 --open \
    > "$PID_DIR/frontend.log" 2>&1 &
echo $! > "$PID_DIR/frontend.pid"
echo "       PID $(cat "$PID_DIR/frontend.pid") — logs: .demo-pids/frontend.log"

sleep 2
echo ""
echo "=== Demo Running ==="
echo ""
echo "  Frontend:  http://localhost:5173"
echo "  Backend:   http://localhost:8080"
echo "  WebSocket: ws://localhost:8080/ws"
echo ""
echo "  Controls:  Ctrl+D to open DevPanel"
echo "  Voice:     Trigger incident → wait for CALLING → click 'Start Mic'"
echo "  Passphrase: \"REDACTED_PASSPHRASE\""
echo ""
echo "  Stop with: scripts/demo-stop.sh

  --- Production (deployed) ---
  Same-origin: http://rca-nlb-ws-pub-dev01-XXXXXXXXXXXXXXXX.elb.eu-west-1.amazonaws.com
  CloudFront:  https://XXXXXXXXXXXX.cloudfront.net (auth: demo / REDACTED_PASSWORD)"
