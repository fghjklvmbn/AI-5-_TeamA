[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath($PSScriptRoot)
$SharedRoot = [IO.Path]::GetFullPath((Join-Path $Root "..\.."))
$Python = Join-Path $SharedRoot ".venv\Scripts\python.exe"
$Runtime = Join-Path $Root ".runtime"
$Logs = Join-Path $Runtime "logs"
$Gateway = Join-Path $Root "backend\gateway"
$Archive = Join-Path $Root "backend\archive_service"
$Frontend = Join-Path $Root "frontend"
$Admin = Join-Path $Root "admin"

function Import-DotEnv([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    foreach ($Line in [IO.File]::ReadAllLines($Path)) {
        $Value = $Line.Trim()
        if (-not $Value -or $Value.StartsWith("#") -or -not $Value.Contains("=")) { continue }
        $Pair = $Value.Split("=", 2)
        [Environment]::SetEnvironmentVariable($Pair[0].Trim(), $Pair[1].Trim(), "Process")
    }
}

function Test-Http([string]$Uri) {
    try {
        $Response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 3
        return $Response.StatusCode -ge 200 -and $Response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Wait-Http(
    [string]$Name,
    [string]$Uri,
    [Diagnostics.Process]$Process
) {
    for ($Attempt = 0; $Attempt -lt 60; $Attempt++) {
        if ($Process.HasExited) {
            throw "$Name 프로세스가 시작 직후 종료되었습니다."
        }
        if (Test-Http $Uri) { return }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name 상태 확인 시간이 초과되었습니다: $Uri"
}

function Start-ServiceProcess(
    [string]$Name,
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$WorkingDirectory,
    [string]$HealthUri
) {
    if (Test-Http $HealthUri) {
        Write-Host "$Name 서비스가 이미 실행 중입니다: $HealthUri" -ForegroundColor Yellow
        return
    }

    $PidFile = Join-Path $Runtime "$Name.pid"
    if (Test-Path -LiteralPath $PidFile) {
        Remove-Item -LiteralPath $PidFile -Force
    }
    $QuotedArguments = $ArgumentList | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    }
    $StartInfo = New-Object Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $FilePath
    $StartInfo.Arguments = $QuotedArguments -join " "
    $StartInfo.WorkingDirectory = $WorkingDirectory
    $StartInfo.UseShellExecute = $true
    $StartInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    $Process = [Diagnostics.Process]::Start($StartInfo)
    [IO.File]::WriteAllText($PidFile, [string]$Process.Id)
    Wait-Http $Name $HealthUri $Process
    Write-Host "$Name 시작 완료 (PID $($Process.Id))" -ForegroundColor Green
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "공용 Python 가상환경이 없습니다: $Python"
}
if (-not (Test-Path -LiteralPath (Join-Path $Frontend "node_modules"))) {
    throw "프로젝트 3 Frontend 패키지가 설치되지 않았습니다."
}
if (-not (Test-Path -LiteralPath (Join-Path $Admin "node_modules"))) {
    throw "프로젝트 3 Admin 패키지가 설치되지 않았습니다."
}
if (-not (Test-Path -LiteralPath (Join-Path $Frontend "dist\index.html"))) {
    throw "프로젝트 3 Frontend 빌드가 없습니다."
}
if (-not (Test-Path -LiteralPath (Join-Path $Admin "dist\index.html"))) {
    throw "프로젝트 3 Admin 빌드가 없습니다."
}

Import-DotEnv (Join-Path $SharedRoot ".env")
Import-DotEnv (Join-Path $SharedRoot ".env.beta_project3.backup")

$TokenFile = Join-Path $Runtime "archive-service-token"
if (Test-Path -LiteralPath $TokenFile) {
    $ArchiveToken = [IO.File]::ReadAllText($TokenFile).Trim()
} else {
    $Bytes = New-Object byte[] 48
    $Rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $Rng.GetBytes($Bytes) } finally { $Rng.Dispose() }
    $ArchiveToken = [Convert]::ToBase64String($Bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
    New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
    [IO.File]::WriteAllText($TokenFile, $ArchiveToken)
}

[Environment]::SetEnvironmentVariable("MEMORYPAL_ARCHIVE_SERVICE_TOKEN", $ArchiveToken, "Process")
[Environment]::SetEnvironmentVariable("MEMORYPAL_DATABASE_PATH", (Join-Path $SharedRoot "backend\gateway\data\memorypal.db"), "Process")
[Environment]::SetEnvironmentVariable("MEMORYPAL_DATABASE_URL", "", "Process")
[Environment]::SetEnvironmentVariable("MEMORYPAL_TASK_QUEUE_MODE", "local", "Process")
[Environment]::SetEnvironmentVariable("MEMORYPAL_REDIS_URL", "", "Process")
[Environment]::SetEnvironmentVariable("MEMORYPAL_REDIS_PREFIX", "memorypal-project3", "Process")
[Environment]::SetEnvironmentVariable("MEMORYPAL_ROOT_PATH", "/api_memoripal/project3/gateway", "Process")
[Environment]::SetEnvironmentVariable("MEMORYPAL_CORS_ORIGINS", "https://developark.duckdns.org,http://127.0.0.1:8083,http://127.0.0.1:8082", "Process")
[Environment]::SetEnvironmentVariable("MEMORYPAL_STT_URL", "http://127.0.0.1:8001", "Process")
[Environment]::SetEnvironmentVariable("MEMORYPAL_TTS_URL", "http://127.0.0.1:8003", "Process")
[Environment]::SetEnvironmentVariable("MEMORYPAL_ARCHIVE_URL", "http://127.0.0.1:8006", "Process")
[Environment]::SetEnvironmentVariable("MEMORYPAL_ARCHIVE_PRIVATE_UPLOAD_DIR", (Join-Path $SharedRoot "backend\archive_service\private_voice_uploads"), "Process")
[Environment]::SetEnvironmentVariable("EXPO_PUBLIC_API_URL", "https://developark.duckdns.org/api_memoripal/project3/gateway/v1", "Process")
[Environment]::SetEnvironmentVariable("MEMORYPAL_ADMIN_PORT", "8082", "Process")
[Environment]::SetEnvironmentVariable("VITE_API_URL", "https://developark.duckdns.org/api_memoripal/project3/gateway/v1", "Process")

New-Item -ItemType Directory -Force -Path $Logs | Out-Null

Write-Host "MemoryPal 프로젝트 3 병렬 실행" -ForegroundColor Cyan
Write-Host "공용 서비스: STT 8001, TTS 8003, 외부 LLM"

Start-ServiceProcess `
    -Name "archive-project3" `
    -FilePath $Python `
    -ArgumentList @("-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8006") `
    -WorkingDirectory $Archive `
    -HealthUri "http://127.0.0.1:8006/health"

Start-ServiceProcess `
    -Name "gateway-project3" `
    -FilePath $Python `
    -ArgumentList @(
        (Join-Path $Root "scripts\gateway_server.py"),
        "--host", "0.0.0.0",
        "--port", "8010",
        "--log-file", (Join-Path $Logs "gateway.log")
    ) `
    -WorkingDirectory $Gateway `
    -HealthUri "http://127.0.0.1:8010/v1/health"

Start-ServiceProcess `
    -Name "frontend-project3" `
    -FilePath $Python `
    -ArgumentList @(
        (Join-Path $Root "scripts\static_server.py"),
        "--directory", (Join-Path $Frontend "dist"),
        "--host", "0.0.0.0",
        "--port", "8083",
        "--prefix", "/api_memoripal/project3/main",
        "--log-file", (Join-Path $Logs "frontend.log")
    ) `
    -WorkingDirectory $Root `
    -HealthUri "http://127.0.0.1:8083/"

$Node = (Get-Command node.exe -ErrorAction Stop).Source
Start-ServiceProcess `
    -Name "admin-project3" `
    -FilePath $Node `
    -ArgumentList @((Join-Path $Admin "server.mjs")) `
    -WorkingDirectory $Admin `
    -HealthUri "http://127.0.0.1:8082/"

Write-Host ""
Write-Host "프로젝트 3 서비스가 실행 중입니다." -ForegroundColor Green
Write-Host "Frontend : http://127.0.0.1:8083/api_memoripal/project3/main/"
Write-Host "Gateway  : http://127.0.0.1:8010/v1/health"
Write-Host "Admin    : http://127.0.0.1:8082/api_memoripal/project3/manage/"
Write-Host "Archive  : http://127.0.0.1:8006/health"
