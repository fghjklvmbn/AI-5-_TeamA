#!/usr/bin/env bash
set -Eeuo pipefail

project_root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
env_file="$project_root/.runtime/model-node.env"
accelerator=auto
role=all
no_build=false
public_url=""

usage() {
  cat <<'EOF'
Usage: bash ./docker-model-node-up.sh [options]
  --stt-only                 Run only STT behind Nginx.
  --tts-only                 Run only TTS behind Nginx.
  --cpu-only | --nvidia | --amd
  --public-url URL           Public base URL, e.g. http://192.168.0.20:8090
  --no-build
EOF
}

while (($#)); do
  case "$1" in
    --stt-only) role=stt ;;
    --tts-only) role=tts ;;
    --cpu-only) accelerator=cpu ;;
    --nvidia) accelerator=nvidia ;;
    --amd) accelerator=rocm ;;
    --public-url) shift; public_url="${1:?--public-url requires a URL}" ;;
    --no-build) no_build=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

cd "$project_root"
mkdir -p .runtime
if [[ ! -f "$env_file" ]]; then
  umask 077
  if command -v openssl >/dev/null 2>&1; then
    token="$(openssl rand -hex 48)"
  else
    token="$(od -An -N48 -tx1 /dev/urandom | tr -d ' \n')"
  fi
  {
    echo "MEMORYPAL_MODEL_SERVICE_TOKEN=$token"
    echo "MEMORYPAL_MODEL_PUBLIC_URL=http://127.0.0.1:8090"
    echo "MEMORYPAL_MODEL_BIND_ADDRESS=0.0.0.0"
    echo "MEMORYPAL_MODEL_PROXY_PORT=8090"
  } > "$env_file"
fi
if ! grep -Eq '^MEMORYPAL_MODEL_SERVICE_TOKEN=.{32,}$' "$env_file"; then
  echo "Set a model token of at least 32 characters in $env_file" >&2
  exit 1
fi
if [[ -n "$public_url" ]]; then
  export MEMORYPAL_MODEL_PUBLIC_URL="${public_url%/}"
fi
if [[ "$accelerator" == auto ]]; then
  if [[ -e /dev/kfd && -d /dev/dri ]]; then accelerator=rocm
  elif command -v nvidia-smi >/dev/null 2>&1 \
    && nvidia-smi >/dev/null 2>&1 \
    && docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -qi nvidia; then accelerator=nvidia
  else accelerator=cpu
  fi
fi

compose=(docker compose --env-file "$env_file" -f docker-compose.model-node.yml)
if [[ "$accelerator" == nvidia ]]; then compose+=(-f docker-compose.nvidia.yml)
elif [[ "$accelerator" == rocm ]]; then compose+=(-f docker-compose.rocm.yml)
fi
services=(nginx)
if [[ "$role" != tts ]]; then services+=(stt); fi
if [[ "$role" != stt ]]; then services+=(tts); fi
up=(up -d --wait --wait-timeout 3600)
if [[ "$no_build" == false ]]; then up+=(--build); fi
"${compose[@]}" config --quiet
"${compose[@]}" "${up[@]}" "${services[@]}"
echo "Model node: ${MEMORYPAL_MODEL_PUBLIC_URL:-$(grep '^MEMORYPAL_MODEL_PUBLIC_URL=' "$env_file" | cut -d= -f2-)}"
echo "Accelerator: $accelerator; role: $role"
echo "Copy MEMORYPAL_MODEL_SERVICE_TOKEN from $env_file to the main server."
