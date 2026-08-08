[CmdletBinding()]
param(
    [switch]$NoBuild,
    [switch]$SttOnly,
    [switch]$TtsOnly,
    [switch]$CpuOnly,
    [switch]$Nvidia,
    [switch]$Amd,
    [string]$PublicUrl = ""
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if ($SttOnly -and $TtsOnly) { throw "Choose only one of -SttOnly or -TtsOnly." }
if ($Nvidia -and $CpuOnly) { throw "Choose only one of -Nvidia or -CpuOnly." }
if ($Amd) { throw "ROCm Docker model nodes require native Linux. Use Linux --amd or Windows CPU/NVIDIA." }
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtime = Join-Path $root ".runtime"
$envFile = Join-Path $runtime "model-node.env"
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
if (-not (Test-Path -LiteralPath $envFile)) {
    $bytes = New-Object byte[] 48
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    $token = -join ($bytes | ForEach-Object { $_.ToString("x2") })
    [IO.File]::WriteAllLines($envFile, @(
        "MEMORYPAL_MODEL_SERVICE_TOKEN=$token",
        "MEMORYPAL_MODEL_PUBLIC_URL=http://127.0.0.1:8090",
        "MEMORYPAL_MODEL_BIND_ADDRESS=0.0.0.0",
        "MEMORYPAL_MODEL_PROXY_PORT=8090"
    ), [Text.UTF8Encoding]::new($false))
}
if ($PublicUrl) { $env:MEMORYPAL_MODEL_PUBLIC_URL = $PublicUrl.TrimEnd("/") }
$files = @("docker-compose.model-node.yml")
$accelerator = "cpu"
$nvidiaAvailable = $false
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    & nvidia-smi *> $null
    if ($LASTEXITCODE -eq 0) {
        $runtimes = & docker info --format "{{json .Runtimes}}" 2>$null
        $nvidiaAvailable = $LASTEXITCODE -eq 0 -and $runtimes -match "nvidia"
    }
}
if ($Nvidia -or (-not $CpuOnly -and $nvidiaAvailable)) {
    $files += "docker-compose.nvidia.yml"
    $accelerator = "nvidia"
}
$services = @("nginx")
if (-not $TtsOnly) { $services += "stt" }
if (-not $SttOnly) { $services += "tts" }
$args = @("compose", "--env-file", $envFile)
foreach ($file in $files) { $args += @("-f", (Join-Path $root $file)) }
$args += @("up", "-d", "--wait", "--wait-timeout", "3600")
if (-not $NoBuild) { $args += "--build" }
$args += $services
Push-Location $root
try { & docker @args; if ($LASTEXITCODE -ne 0) { throw "Model node startup failed." } }
finally { Pop-Location }
Write-Host "Model node is running through Nginx on port 8090 ($accelerator)."
Write-Host "Copy MEMORYPAL_MODEL_SERVICE_TOKEN from $envFile to the main server."
