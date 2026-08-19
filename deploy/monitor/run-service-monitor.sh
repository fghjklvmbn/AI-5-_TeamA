#!/usr/bin/env sh
set -eu
if [ "$#" -lt 5 ]; then
  echo "Usage: $0 <stt|llm|tts|gateway|archive> <port> <target-pid> <health-url> <token-file> [--gpu]" >&2
  exit 2
fi
SERVICE=$1
PORT=$2
TARGET_PID=$3
HEALTH_URL=$4
TOKEN_FILE=$5
GPU_FLAG=${6:-}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
export MEMORYPAL_MODEL_SERVICE_TOKEN_FILE="$TOKEN_FILE"
exec python3 "$ROOT/backend/monitor_agent/server.py" \
  --service "$SERVICE" --host 0.0.0.0 --port "$PORT" \
  --target-pid "$TARGET_PID" --health-url "$HEALTH_URL" \
  --log-path "$ROOT/.runtime/logs/$SERVICE.hardware.jsonl" $GPU_FLAG
