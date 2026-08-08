[CmdletBinding()]
param(
    [switch]$NoBuild,
    [switch]$WithModels,
    [switch]$CpuOnly,
    [switch]$Nvidia,
    [switch]$Amd
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDirectory = Join-Path $ProjectRoot ".runtime"
$DockerEnvFile = Join-Path $RuntimeDirectory "docker.env"
$ScaleComposeFile = Join-Path $ProjectRoot "docker-compose.scale.yml"
$AppComposeFile = Join-Path $ProjectRoot "docker-compose.app.yml"
$ModelsComposeFile = Join-Path $ProjectRoot "docker-compose.models.yml"
$NvidiaComposeFile = Join-Path $ProjectRoot "docker-compose.nvidia.yml"
$ComposeFiles = @($ScaleComposeFile, $AppComposeFile)

function New-MemoryPalSecret {
    $bytes = New-Object byte[] 48
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return -join ($bytes | ForEach-Object { $_.ToString("x2") })
}

function Initialize-DockerEnvironment {
    New-Item -ItemType Directory -Force -Path $RuntimeDirectory | Out-Null
    if (Test-Path -LiteralPath $DockerEnvFile) {
        $configured = @{}
        foreach ($line in [IO.File]::ReadAllLines($DockerEnvFile)) {
            if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
                $configured[$Matches[1]] = $Matches[2]
            }
        }
        $required = @(
            "MEMORYPAL_POSTGRES_PASSWORD",
            "MEMORYPAL_REDIS_PASSWORD",
            "MEMORYPAL_JWT_SECRET",
            "MEMORYPAL_MODEL_SERVICE_TOKEN",
            "MEMORYPAL_ARCHIVE_SERVICE_TOKEN"
        )
        $missing = @($required | Where-Object {
            -not $configured.ContainsKey($_) -or [string]::IsNullOrWhiteSpace($configured[$_])
        })
        if ($missing.Count -gt 0) {
            throw "Docker environment is missing required values: $($missing -join ', '). Remove $DockerEnvFile and run again, or fill them manually."
        }
        return
    }

    $lines = @(
        "# Generated locally by docker-up.ps1. Do not commit this file.",
        "MEMORYPAL_POSTGRES_PASSWORD=$(New-MemoryPalSecret)",
        "MEMORYPAL_REDIS_PASSWORD=$(New-MemoryPalSecret)",
        "MEMORYPAL_JWT_SECRET=$(New-MemoryPalSecret)",
        "MEMORYPAL_MODEL_SERVICE_TOKEN=$(New-MemoryPalSecret)",
        "MEMORYPAL_ARCHIVE_SERVICE_TOKEN=$(New-MemoryPalSecret)"
    )
    [IO.File]::WriteAllLines(
        $DockerEnvFile,
        $lines,
        [Text.UTF8Encoding]::new($false)
    )
}

function Invoke-MemoryPalCompose {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $dockerArguments = @("compose", "--env-file", $DockerEnvFile)
    foreach ($composeFile in $ComposeFiles) {
        $dockerArguments += @("-f", $composeFile)
    }
    $dockerArguments += $Arguments
    & docker @dockerArguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed with exit code $LASTEXITCODE"
    }
}

function Test-NvidiaDocker {
    if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
        return $false
    }
    & nvidia-smi *> $null
    if ($LASTEXITCODE -ne 0) {
        return $false
    }
    $runtimes = & docker info --format "{{json .Runtimes}}" 2>$null
    return $LASTEXITCODE -eq 0 -and $runtimes -match "nvidia"
}

Push-Location $ProjectRoot
try {
    docker info --format "Docker Engine {{.ServerVersion}}" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop is not running. Start Docker Desktop with Linux containers and try again."
    }

    Initialize-DockerEnvironment

    if ($Amd) {
        throw "AMD ROCm containers require a native Linux Docker host. On Windows, use AMD's native ROCm PyTorch model servers or omit -Amd to use CPU containers."
    }
    if ($Nvidia -and $CpuOnly) {
        throw "Choose only one of -Nvidia or -CpuOnly."
    }
    if ($Nvidia -or $CpuOnly) {
        $WithModels = $true
    }

    $modelAccelerator = "external"
    $modelServices = @()
    if ($WithModels) {
        $ComposeFiles += $ModelsComposeFile
        $modelServices = @("stt", "tts")
        $useNvidia = $Nvidia -or (-not $CpuOnly -and (Test-NvidiaDocker))
        if ($useNvidia) {
            $ComposeFiles += $NvidiaComposeFile
            $modelAccelerator = "nvidia"
        }
        else {
            $modelAccelerator = "cpu"
            if (-not $CpuOnly) {
                $displayAdapters = @(Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue)
                if ($displayAdapters.Name -match "AMD|Radeon") {
                    Write-Warning "AMD GPU detected. Docker ROCm device passthrough is supported by this project on native Linux; Windows Docker Desktop will use CPU."
                }
            }
        }
        Write-Host "Model accelerator: $modelAccelerator" -ForegroundColor Cyan
    }

    Invoke-MemoryPalCompose -Arguments @("config", "--quiet")

    Write-Host "Starting PostgreSQL and Redis..." -ForegroundColor Cyan
    Invoke-MemoryPalCompose -Arguments @(
        "up", "-d", "--wait", "--wait-timeout", "180", "postgres", "redis"
    )

    Write-Host "Applying database migrations..." -ForegroundColor Cyan
    Invoke-MemoryPalCompose -Arguments @(
        "--profile", "tools", "run", "--rm", "migrate"
    )

    Write-Host "Building and starting MemoryPal..." -ForegroundColor Cyan
    $upArguments = @("up", "-d")
    if (-not $NoBuild) {
        $upArguments += "--build"
    }
    $waitTimeout = if ($WithModels) { "3600" } else { "600" }
    $upArguments += @(
        "--wait", "--wait-timeout", $waitTimeout,
        "archive", "gateway", "worker", "frontend", "admin"
    )
    $upArguments += $modelServices
    Invoke-MemoryPalCompose -Arguments $upArguments

    Invoke-MemoryPalCompose -Arguments @("ps")

    Write-Host ""
    Write-Host "MemoryPal is running." -ForegroundColor Green
    Write-Host "Frontend : http://127.0.0.1:8081/api_memoripal/main/"
    Write-Host "Admin    : http://127.0.0.1:8082/api_memoripal/manage/"
    Write-Host "Gateway  : http://127.0.0.1:8000/v1/health"
    Write-Host "API docs : http://127.0.0.1:8000/docs"
    Write-Host ""
    Write-Host "The local admin allowlist defaults to admin@memorypal.local."
    if ($WithModels) {
        Write-Host "STT      : http://127.0.0.1:8001/health ($modelAccelerator)"
        Write-Host "TTS      : http://127.0.0.1:8003/health ($modelAccelerator)"
    }
    else {
        Write-Host "STT/TTS  : host.docker.internal (use -WithModels to run bundled services)"
    }
    Write-Host "LLM      : host.docker.internal:1234/v1"
}
catch {
    Write-Host "MemoryPal Docker startup failed: $($_.Exception.Message)" -ForegroundColor Red
    if (Test-Path -LiteralPath $DockerEnvFile) {
        $statusArguments = @("compose", "--env-file", $DockerEnvFile)
        foreach ($composeFile in $ComposeFiles) {
            $statusArguments += @("-f", $composeFile)
        }
        $statusArguments += "ps"
        & docker @statusArguments
    }
    throw
}
finally {
    Pop-Location
}
