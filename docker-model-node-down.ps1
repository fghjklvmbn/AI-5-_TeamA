$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
& docker compose --env-file (Join-Path $root ".runtime/model-node.env") -f (Join-Path $root "docker-compose.model-node.yml") down --remove-orphans
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
