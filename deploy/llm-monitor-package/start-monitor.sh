#!/usr/bin/env sh
set -eu
PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TOKEN_FILE=${1:?Usage: ./start-monitor.sh /path/to/model-service-token [port]}
PORT=${2:-8101}
if [ ! -x "$PACKAGE_DIR/.venv/bin/python" ]; then
  python3 -m venv "$PACKAGE_DIR/.venv"
  "$PACKAGE_DIR/.venv/bin/pip" install --disable-pip-version-check -r "$PACKAGE_DIR/requirements.txt"
fi
export MEMORYPAL_MODEL_SERVICE_TOKEN_FILE="$TOKEN_FILE"
exec "$PACKAGE_DIR/.venv/bin/python" "$PACKAGE_DIR/server.py" \
  --service llm --host 0.0.0.0 --port "$PORT" \
  --process-names "lm-studio,lms,llmster" \
  --health-url http://127.0.0.1:1234/api/v1/models \
  --gpu --log-path "$PACKAGE_DIR/runtime/llm.hardware.jsonl" \
  --lmstudio-log-path "$PACKAGE_DIR/runtime/llm.lmstudio.jsonl" \
  --lmstudio-log-sources "server,runtime,model"
