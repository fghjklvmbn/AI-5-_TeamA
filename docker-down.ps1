[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DockerEnvFile = Join-Path $ProjectRoot ".runtime\docker.env"
$ScaleComposeFile = Join-Path $ProjectRoot "docker-compose.scale.yml"
$AppComposeFile = Join-Path $ProjectRoot "docker-compose.app.yml"
$ModelsComposeFile = Join-Path $ProjectRoot "docker-compose.models.yml"

if (-not (Test-Path -LiteralPath $DockerEnvFile)) {
    throw "Docker environment not found: $DockerEnvFile"
}

Push-Location $ProjectRoot
try {
    & docker compose `
        --env-file $DockerEnvFile `
        -f $ScaleComposeFile `
        -f $AppComposeFile `
        -f $ModelsComposeFile `
        down --remove-orphans
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose down failed with exit code $LASTEXITCODE"
    }
    Write-Host "MemoryPal containers stopped. Database and upload volumes were preserved." -ForegroundColor Green
}
finally {
    Pop-Location
}
