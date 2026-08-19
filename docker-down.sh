#!/usr/bin/env bash
set -Eeuo pipefail

project_root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
docker_env_file="$project_root/.runtime/docker.env"

if [[ ! -f "$docker_env_file" ]]; then
  echo "Docker environment not found: $docker_env_file" >&2
  exit 1
fi

cd "$project_root"
docker compose \
  --env-file "$docker_env_file" \
  -f "$project_root/docker-compose.scale.yml" \
  -f "$project_root/docker-compose.app.yml" \
  -f "$project_root/docker-compose.models.yml" \
  down --remove-orphans

echo "MemoryPal containers stopped. Database, model cache, and upload volumes were preserved."

