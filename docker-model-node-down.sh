#!/usr/bin/env bash
set -Eeuo pipefail
project_root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_root"
docker compose --env-file .runtime/model-node.env -f docker-compose.model-node.yml down --remove-orphans
