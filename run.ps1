[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath($PSScriptRoot)
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$Gateway = Join-Path $Root "backend\gateway"
$Stt = Join-Path $Root "backend\STT_backend_server"
$Tts = Join-Path $Root "backend\TTS_Server"
$Archive = Join-Path $Root "backend\archive_service"
$Frontend = Join-Path $Root "frontend"
$Admin = Join-Path $Root "admin"
$RootEnv = Join-Path $Root ".env"
$Runtime = Join-Path $Root ".runtime"
$Logs = Join-Path $Runtime "logs"
$ArchiveServiceTokenFile = Join-Path $Runtime "archive-service-token"
$ArchiveServiceTokenFromCaller = [Environment]::GetEnvironmentVariable(
    "MEMORYPAL_ARCHIVE_SERVICE_TOKEN", "Process"
)

function Import-DotEnv([string]$Path) {
    foreach ($Line in [IO.File]::ReadAllLines($Path)) {
        $Value = $Line.Trim()
        if (-not $Value -or $Value.StartsWith("#") -or -not $Value.Contains("=")) { continue }
        $Pair = $Value.Split('=', 2)
        [Environment]::SetEnvironmentVariable($Pair[0].Trim(), $Pair[1].Trim(), "Process")
    }
}

function Initialize-ArchiveServiceToken([string]$TokenPath) {
    $VariableName = "MEMORYPAL_ARCHIVE_SERVICE_TOKEN"
    $ConfiguredToken = [Environment]::GetEnvironmentVariable($VariableName, "Process")
    if (-not [String]::IsNullOrWhiteSpace($ConfiguredToken)) {
        # A token supplied by the caller or root .env is authoritative. In
        # particular, do not replace a persisted local token in this case.
        [Environment]::SetEnvironmentVariable($VariableName, $ConfiguredToken, "Process")
        Write-Host "Archive service token: process/.env setting in use"
        return
    }

    New-Item -ItemType Directory -Force -Path (Split-Path $TokenPath -Parent) | Out-Null
    $RuntimeToken = $null
    if (Test-Path -LiteralPath $TokenPath) {
        $RuntimeToken = [IO.File]::ReadAllText($TokenPath).Trim()
    }

    if ([String]::IsNullOrWhiteSpace($RuntimeToken)) {
        $TokenBytes = New-Object byte[] 48
        $Random = [Security.Cryptography.RandomNumberGenerator]::Create()
        try {
            $Random.GetBytes($TokenBytes)
        } finally {
            $Random.Dispose()
        }
        $RuntimeToken = [Convert]::ToBase64String($TokenBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
        [IO.File]::WriteAllText($TokenPath, $RuntimeToken)
        Write-Host "Archive service token: generated in ignored runtime storage"
    } else {
        Write-Host "Archive service token: reused from ignored runtime storage"
    }

    # Process-scoped environment variables are inherited by every service
    # launched below, so Gateway and Archive receive the exact same token.
    [Environment]::SetEnvironmentVariable($VariableName, $RuntimeToken, "Process")
}

function Resolve-CondaPython([string]$EnvironmentName) {
    $Conda = Get-Command conda.exe -ErrorAction SilentlyContinue
    if ($null -eq $Conda) {
        $Conda = Get-Command conda -ErrorAction SilentlyContinue
    }
    if ($null -eq $Conda) {
        throw "Conda를 찾을 수 없습니다. $EnvironmentName 환경을 먼저 준비해 주세요."
    }

    $EnvironmentList = (& $Conda.Source env list --json | ConvertFrom-Json).envs
    $EnvironmentPath = $EnvironmentList | Where-Object {
        (Split-Path $_ -Leaf).Equals($EnvironmentName, [StringComparison]::OrdinalIgnoreCase)
    } | Select-Object -First 1
    if (-not $EnvironmentPath) {
        throw "Conda $EnvironmentName 환경이 없습니다. 해당 음성 서버 환경을 먼저 설치해 주세요."
    }

    $Python = Join-Path $EnvironmentPath "python.exe"
    if (-not (Test-Path -LiteralPath $Python)) {
        throw "Conda $EnvironmentName 환경의 Python을 찾을 수 없습니다: $Python"
    }
    return $Python
}

function Test-Http([string]$Uri) {
    try {
        $Response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2
        return $Response.StatusCode -ge 200 -and $Response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Wait-Http(
    [string]$Name,
    [string]$Uri,
    [Diagnostics.Process]$Process,
    [int]$Attempts = 30
) {
    for ($Attempt = 0; $Attempt -lt $Attempts; $Attempt++) {
        if ($Process.HasExited) {
            throw "$Name 프로세스가 시작 직후 종료되었습니다. 로그를 확인해 주세요."
        }
        if (Test-Http $Uri) { return }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name 상태 확인 시간이 초과되었습니다: $Uri"
}

function Start-MemoryPalProcess(
    [string]$Name,
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$WorkingDirectory,
    [string]$PidFile,
    [string]$HealthUri,
    [int]$HealthAttempts = 30
) {
    if (Test-Http $HealthUri) {
        Write-Host "$Name 서비스가 이미 실행 중입니다: $HealthUri" -ForegroundColor Yellow
        return
    }

    if (Test-Path -LiteralPath $PidFile) {
        Remove-Item -LiteralPath $PidFile -Force
    }
    $QuotedArguments = $ArgumentList | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    }
    $StartInfo = New-Object Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $FilePath
    $StartInfo.Arguments = $QuotedArguments -join ' '
    $StartInfo.WorkingDirectory = $WorkingDirectory
    $StartInfo.UseShellExecute = $true
    $StartInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    Write-Host "$Name 서비스를 시작합니다: $HealthUri"
    $Process = [Diagnostics.Process]::Start($StartInfo)
    [IO.File]::WriteAllText($PidFile, [string]$Process.Id)
    Wait-Http $Name $HealthUri $Process $HealthAttempts
    Write-Host "$Name 시작 완료 (PID $($Process.Id))" -ForegroundColor Green
}

function Start-MemoryPalBackgroundProcess(
    [string]$Name,
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$WorkingDirectory,
    [string]$PidFile
) {
    if (Test-Path -LiteralPath $PidFile) {
        $ExistingId = 0
        $ExistingText = [IO.File]::ReadAllText($PidFile).Trim()
        if ([int]::TryParse($ExistingText, [ref]$ExistingId)) {
            $Existing = Get-Process -Id $ExistingId -ErrorAction SilentlyContinue
            if ($null -ne $Existing -and -not $Existing.HasExited) {
                Write-Host "$Name 서비스가 이미 실행 중입니다 (PID $ExistingId)" -ForegroundColor Yellow
                return
            }
        }
        Remove-Item -LiteralPath $PidFile -Force
    }
    $QuotedArguments = $ArgumentList | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    }
    $StartInfo = New-Object Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $FilePath
    $StartInfo.Arguments = $QuotedArguments -join ' '
    $StartInfo.WorkingDirectory = $WorkingDirectory
    $StartInfo.UseShellExecute = $true
    $StartInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    Write-Host "$Name 백그라운드 서비스를 시작합니다."
    $Process = [Diagnostics.Process]::Start($StartInfo)
    Start-Sleep -Milliseconds 1200
    if ($Process.HasExited) {
        throw "$Name 프로세스가 시작 직후 종료되었습니다. 로그를 확인해 주세요."
    }
    [IO.File]::WriteAllText($PidFile, [string]$Process.Id)
    Write-Host "$Name 시작 완료 (PID $($Process.Id))" -ForegroundColor Green
}

try {
    if (-not (Test-Path -LiteralPath $RootEnv)) {
        throw "루트 .env가 없습니다. 먼저 install.cmd를 실행해 주세요."
    }
    Import-DotEnv $RootEnv
    if (-not [String]::IsNullOrWhiteSpace($ArchiveServiceTokenFromCaller)) {
        # An explicitly injected process secret takes precedence over .env.
        [Environment]::SetEnvironmentVariable(
            "MEMORYPAL_ARCHIVE_SERVICE_TOKEN", $ArchiveServiceTokenFromCaller, "Process"
        )
    }
    Initialize-ArchiveServiceToken $ArchiveServiceTokenFile
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        throw "Python 가상환경이 없습니다. 먼저 install.cmd를 실행해 주세요."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Frontend "node_modules"))) {
        throw "Frontend 패키지가 없습니다. 먼저 install.cmd를 실행해 주세요."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Frontend "dist\index.html"))) {
        throw "Frontend 빌드가 없습니다. 먼저 install.cmd를 실행해 주세요."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Admin "node_modules"))) {
        throw "관리자 페이지 패키지가 없습니다. 먼저 install.cmd를 실행해 주세요."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Admin "dist\index.html"))) {
        throw "관리자 페이지 빌드가 없습니다. 먼저 install.cmd를 실행해 주세요."
    }
    $NodeCommand = Get-Command node.exe -ErrorAction Stop
    [Environment]::SetEnvironmentVariable("MEMORYPAL_ADMIN_PORT", "8082", "Process")
    New-Item -ItemType Directory -Force -Path $Logs | Out-Null

    $SttPython = Resolve-CondaPython "STT"
    $TtsPython = Resolve-CondaPython "qwen3-tts"
    $ArchivePython = Resolve-CondaPython "archive"

    Write-Host "MemoryPal Frontend + Backend 통합 실행" -ForegroundColor Cyan

    Start-MemoryPalProcess `
        -Name "gateway" `
        -FilePath $VenvPython `
        -ArgumentList @(
            (Join-Path $Root "scripts\gateway_server.py"), "--host", "0.0.0.0", "--port", "8000",
            "--log-file", (Join-Path $Logs "gateway.log")
        ) `
        -WorkingDirectory $Gateway `
        -PidFile (Join-Path $Runtime "gateway.pid") `
        -HealthUri "http://127.0.0.1:8000/v1/health"

    $TaskQueueMode = [Environment]::GetEnvironmentVariable(
        "MEMORYPAL_TASK_QUEUE_MODE", "Process"
    )
    if ($TaskQueueMode -and $TaskQueueMode.Equals("redis", [StringComparison]::OrdinalIgnoreCase)) {
        Start-MemoryPalBackgroundProcess `
            -Name "portrait-worker" `
            -FilePath $VenvPython `
            -ArgumentList @(
                (Join-Path $Root "scripts\portrait_worker.py"),
                "--log-file", (Join-Path $Logs "portrait-worker.log")
            ) `
            -WorkingDirectory $Gateway `
            -PidFile (Join-Path $Runtime "portrait-worker.pid")
    }

    Start-MemoryPalProcess `
        -Name "frontend" `
        -FilePath $VenvPython `
        -ArgumentList @(
            (Join-Path $Root "scripts\static_server.py"),
            "--directory", (Join-Path $Frontend "dist"),
            "--host", "0.0.0.0",
            "--port", "8081",
            "--prefix", "/api_memoripal/main",
            "--log-file", (Join-Path $Logs "frontend.log")
        ) `
        -WorkingDirectory $Root `
        -PidFile (Join-Path $Runtime "frontend.pid") `
        -HealthUri "http://127.0.0.1:8081/"

    Start-MemoryPalProcess `
        -Name "admin" `
        -FilePath $NodeCommand.Source `
        -ArgumentList @((Join-Path $Admin "server.mjs")) `
        -WorkingDirectory $Admin `
        -PidFile (Join-Path $Runtime "admin.pid") `
        -HealthUri "http://127.0.0.1:8082/"

    Start-MemoryPalProcess `
        -Name "archive" `
        -FilePath $ArchivePython `
        -ArgumentList @("-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8004") `
        -WorkingDirectory $Archive `
        -PidFile (Join-Path $Runtime "archive.pid") `
        -HealthUri "http://127.0.0.1:8004/health" `
        -HealthAttempts 120

    Start-MemoryPalProcess `
        -Name "stt" `
        -FilePath $SttPython `
        -ArgumentList @("-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001") `
        -WorkingDirectory $Stt `
        -PidFile (Join-Path $Runtime "stt.pid") `
        -HealthUri "http://127.0.0.1:8001/health" `
        -HealthAttempts 120

    Start-MemoryPalProcess `
        -Name "tts" `
        -FilePath $TtsPython `
        -ArgumentList @("-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8003") `
        -WorkingDirectory $Tts `
        -PidFile (Join-Path $Runtime "tts.pid") `
        -HealthUri "http://127.0.0.1:8003/docs" `
        -HealthAttempts 600

    Write-Host "`n모든 애플리케이션 서비스가 실행 중입니다." -ForegroundColor Green
    Write-Host "Frontend : http://127.0.0.1:8081/"
    Write-Host "Admin    : http://127.0.0.1:8082/"
    Write-Host "Gateway  : http://127.0.0.1:8000/v1/health"
    Write-Host "STT      : http://127.0.0.1:8001/health"
    Write-Host "TTS      : http://127.0.0.1:8003/docs"
    Write-Host "Archive  : http://127.0.0.1:8004/health"
    Write-Host "API Docs : http://127.0.0.1:8000/docs"
    Write-Host "Logs     : $Logs"
    Write-Host "External : https://developark.duckdns.org/api_memoripal/manage/"
    if ($TaskQueueMode -and $TaskQueueMode.Equals("redis", [StringComparison]::OrdinalIgnoreCase)) {
        Write-Host "Worker   : Redis 분산 자화상 워커 실행 중"
    }
    Write-Host "`nLLM은 프로젝트 루트 .env 설정을 사용합니다."
    exit 0
} catch {
    Write-Host "`n실행 실패: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "로그 위치: $Logs"
    exit 1
}
