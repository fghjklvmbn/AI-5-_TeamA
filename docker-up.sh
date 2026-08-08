#!/usr/bin/env bash
set -Eeuo pipefail

project_root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
runtime_directory="$project_root/.runtime"
docker_env_file="$runtime_directory/docker.env"

no_build=false
with_models=false
accelerator=auto

usage() {
  cat <<'EOF'
Usage: bash ./docker-up.sh [options]

Options:
  --models       Start the bundled STT and TTS model services.
  --cpu-only     Force model services to use CPU.
  --nvidia       Force NVIDIA CUDA for model services.
  --amd          Force AMD ROCm for model services (Linux only).
  --no-build     Reuse existing application images.
  -h, --help     Show this help.
EOF
}

while (($#)); do
  case "$1" in
    --models) with_models=true ;;
    --cpu-only) accelerator=cpu; with_models=true ;;
    --nvidia) accelerator=nvidia; with_models=true ;;
    --amd) accelerator=rocm; with_models=true ;;
    --no-build) no_build=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

new_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 48
  else
    od -An -N48 -tx1 /dev/urandom | tr -d ' \n'
  fi
}

initialize_docker_environment() {
  mkdir -p "$runtime_directory"
  if [[ ! -f "$docker_env_file" ]]; then
    umask 077
    {
      echo "# Generated locally by docker-up.sh. Do not commit this file."
      echo "MEMORYPAL_POSTGRES_PASSWORD=$(new_secret)"
      echo "MEMORYPAL_REDIS_PASSWORD=$(new_secret)"
      echo "MEMORYPAL_JWT_SECRET=$(new_secret)"
      echo "MEMORYPAL_MODEL_SERVICE_TOKEN=$(new_secret)"
      echo "MEMORYPAL_ARCHIVE_SERVICE_TOKEN=$(new_secret)"
    } > "$docker_env_file"
  fi

  local key
  for key in \
    MEMORYPAL_POSTGRES_PASSWORD \
    MEMORYPAL_REDIS_PASSWORD \
    MEMORYPAL_JWT_SECRET \
    MEMORYPAL_MODEL_SERVICE_TOKEN \
    MEMORYPAL_ARCHIVE_SERVICE_TOKEN; do
    if ! grep -Eq "^${key}=.{32,}$" "$docker_env_file"; then
      echo "Docker environment is missing a strong value for ${key}: ${docker_env_file}" >&2
      exit 1
    fi
  done
}

detect_accelerator() {
  if [[ "$accelerator" != auto ]]; then
    return
  fi
  if [[ -e /dev/kfd && -d /dev/dri ]]; then
    accelerator=rocm
    return
  fi
  if command -v nvidia-smi >/dev/null 2>&1 \
    && nvidia-smi >/dev/null 2>&1 \
    && docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -qi nvidia; then
    accelerator=nvidia
    return
  fi
  accelerator=cpu
}

cd "$project_root"
docker info --format 'Docker Engine {{.ServerVersion}}' >/dev/null
initialize_docker_environment

compose=(
  docker compose
  --env-file "$docker_env_file"
  -f "$project_root/docker-compose.scale.yml"
  -f "$project_root/docker-compose.app.yml"
)

model_services=()
if [[ "$with_models" == true ]]; then
  detect_accelerator
  compose+=(-f "$project_root/docker-compose.models.yml")
  case "$accelerator" in
    nvidia) compose+=(-f "$project_root/docker-compose.nvidia.yml") ;;
    rocm)
      if [[ ! -e /dev/kfd || ! -d /dev/dri ]]; then
        echo "AMD ROCm requires /dev/kfd and /dev/dri on the Linux host." >&2
        exit 1
      fi
      compose+=(-f "$project_root/docker-compose.rocm.yml")
      ;;
    cpu) ;;
  esac
  model_services=(stt tts)
  echo "Model accelerator: $accelerator"
fi

on_error() {
  echo "MemoryPal Docker startup failed." >&2
  "${compose[@]}" ps || true
}
trap on_error ERR

"${compose[@]}" config --quiet
echo "Starting PostgreSQL and Redis..."
"${compose[@]}" up -d --wait --wait-timeout 180 postgres redis

echo "Applying database migrations..."
"${compose[@]}" --profile tools run --rm migrate

echo "Building and starting MemoryPal..."
up_args=(up -d)
if [[ "$no_build" == false ]]; then
  up_args+=(--build)
fi
up_args+=(--wait --wait-timeout 3600 archive gateway worker frontend admin)
up_args+=("${model_services[@]}")
"${compose[@]}" "${up_args[@]}"
"${compose[@]}" ps

trap - ERR
echo
echo "MemoryPal is running."
echo "Frontend : http://127.0.0.1:8081/api_memoripal/main/"
echo "Admin    : http://127.0.0.1:8082/api_memoripal/manage/"
echo "Gateway  : http://127.0.0.1:8000/v1/health"
echo "API docs : http://127.0.0.1:8000/docs"
if [[ "$with_models" == true ]]; then
  echo "STT      : http://127.0.0.1:8001/health ($accelerator)"
  echo "TTS      : http://127.0.0.1:8003/health ($accelerator)"
else
  echo "STT/TTS  : host.docker.internal (use --models to run bundled services)"
fi
echo "LLM      : host.docker.internal:1234/v1"
