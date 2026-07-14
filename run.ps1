[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath($PSScriptRoot)
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$Gateway = Join-Path $Root "backend\gateway"
$Frontend = Join-Path $Root "frontend"
$RootEnv = Join-Path $Root ".env"
$Runtime = Join-Path $Root ".runtime"
$Logs = Join-Path $Runtime "logs"

function Import-DotEnv([string]$Path) {
    foreach ($Line in [IO.File]::ReadAllLines($Path)) {
        $Value = $Line.Trim()
        if (-not $Value -or $Value.StartsWith("#") -or -not $Value.Contains("=")) { continue }
        $Pair = $Value.Split('=', 2)
        [Environment]::SetEnvironmentVariable($Pair[0].Trim(), $Pair[1].Trim(), "Process")
    }
}

function Test-Http([string]$Uri) {
    try {
        $Response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2
        return $Response.StatusCode -ge 200 -and $Response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Wait-Http([string]$Name, [string]$Uri, [Diagnostics.Process]$Process) {
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
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
    [string]$HealthUri
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
    $Process = [Diagnostics.Process]::Start($StartInfo)
    [IO.File]::WriteAllText($PidFile, [string]$Process.Id)
    Wait-Http $Name $HealthUri $Process
    Write-Host "$Name 시작 완료 (PID $($Process.Id))" -ForegroundColor Green
}

try {
    if (-not (Test-Path -LiteralPath $RootEnv)) {
        throw "루트 .env가 없습니다. 먼저 install.cmd를 실행해 주세요."
    }
    Import-DotEnv $RootEnv
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        throw "Python 가상환경이 없습니다. 먼저 install.cmd를 실행해 주세요."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Frontend "node_modules"))) {
        throw "Frontend 패키지가 없습니다. 먼저 install.cmd를 실행해 주세요."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Frontend "dist\index.html"))) {
        throw "Frontend 빌드가 없습니다. 먼저 install.cmd를 실행해 주세요."
    }
    New-Item -ItemType Directory -Force -Path $Logs | Out-Null

    Write-Host "MemoryPal Frontend + Gateway 통합 실행" -ForegroundColor Cyan

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

    Write-Host "`n모든 애플리케이션 서비스가 실행 중입니다." -ForegroundColor Green
    Write-Host "Frontend : http://127.0.0.1:8081/"
    Write-Host "Gateway  : http://127.0.0.1:8000/v1/health"
    Write-Host "API Docs : http://127.0.0.1:8000/docs"
    Write-Host "Logs     : $Logs"
    Write-Host "`nSTT/TTS/Archive/LLM은 프로젝트 루트 .env 설정을 사용합니다."
    exit 0
} catch {
    Write-Host "`n실행 실패: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "로그 위치: $Logs"
    exit 1
}
