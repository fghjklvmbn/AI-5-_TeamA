[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TokenFile,
    [int]$Port = 8101,
    [string]$LmsCli = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = [IO.Path]::GetFullPath($PSScriptRoot)
$TokenPath = [IO.Path]::GetFullPath($TokenFile)
if (-not (Test-Path -LiteralPath $TokenPath)) { throw "Token file not found: $TokenPath" }
if ([IO.File]::ReadAllText($TokenPath).Trim().Length -lt 32) { throw "Token must contain at least 32 characters." }

if ([String]::IsNullOrWhiteSpace($LmsCli)) {
    $LmsCommand = Get-Command lms.exe -ErrorAction SilentlyContinue
    if ($null -eq $LmsCommand) { $LmsCommand = Get-Command lms -ErrorAction SilentlyContinue }
    if ($null -ne $LmsCommand) {
        $LmsPath = $LmsCommand.Source
    } else {
        $BundledLms = Join-Path $env:USERPROFILE ".lmstudio\bin\lms.exe"
        if (-not (Test-Path -LiteralPath $BundledLms)) {
            throw "lms CLI를 찾을 수 없습니다. LM Studio를 한 번 실행한 후 lms bootstrap을 실행하거나 -LmsCli 경로를 지정하세요."
        }
        $LmsPath = [IO.Path]::GetFullPath($BundledLms)
    }
} else {
    $LmsPath = [IO.Path]::GetFullPath($LmsCli)
    if (-not (Test-Path -LiteralPath $LmsPath)) { throw "lms CLI not found: $LmsPath" }
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    python -m venv (Join-Path $Root ".venv")
    & $Python -m pip install --disable-pip-version-check -r (Join-Path $Root "requirements.txt")
}
$Runtime = Join-Path $Root "runtime"
$LogPath = Join-Path $Runtime "llm.hardware.jsonl"
$LmStudioLogPath = Join-Path $Runtime "llm.lmstudio.jsonl"
$PidFile = Join-Path $Runtime "llm-monitor.pid"
$ServerPath = Join-Path $Root "server.py"
$StdOutPath = Join-Path $Runtime "llm-monitor.out.log"
$StdErrPath = Join-Path $Runtime "llm-monitor.err.log"
New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
if (Test-Path -LiteralPath $PidFile) {
    $ExistingId = [int]([IO.File]::ReadAllText($PidFile).Trim())
    if (Get-Process -Id $ExistingId -ErrorAction SilentlyContinue) { throw "Monitor is already running (PID $ExistingId)." }
}

$PreviousTokenFile = [Environment]::GetEnvironmentVariable("MEMORYPAL_MODEL_SERVICE_TOKEN_FILE", "Process")
try {
    [Environment]::SetEnvironmentVariable("MEMORYPAL_MODEL_SERVICE_TOKEN_FILE", $TokenPath, "Process")
    $Process = Start-Process -FilePath $Python -ArgumentList @(
        ('"' + $ServerPath + '"'), "--service", "llm", "--host", "0.0.0.0", "--port", [string]$Port,
        "--process-names", '"LM Studio.exe,lms.exe,llmster.exe"', "--health-url", "http://127.0.0.1:1234/api/v1/models",
        "--gpu", "--log-path", ('"' + $LogPath + '"'),
        "--lms-cli", ('"' + $LmsPath + '"'), "--lmstudio-log-path", ('"' + $LmStudioLogPath + '"'),
        "--lmstudio-log-sources", "server,runtime,model"
    ) -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $StdOutPath `
        -RedirectStandardError $StdErrPath -PassThru
} finally {
    [Environment]::SetEnvironmentVariable("MEMORYPAL_MODEL_SERVICE_TOKEN_FILE", $PreviousTokenFile, "Process")
}
[IO.File]::WriteAllText($PidFile, [string]$Process.Id)
for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
    if ($Process.HasExited) { throw "Monitor exited during startup." }
    try {
        $Response = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/health" -TimeoutSec 2
        if ($Response.StatusCode -eq 200) {
            Write-Host "MemoryPal LLM monitor started on port $Port (PID $($Process.Id))." -ForegroundColor Green
            Write-Host "LM Studio logs: $LmStudioLogPath"
            Write-Host "Log API: http://127.0.0.1:$Port/v1/logs/recent"
            exit 0
        }
    } catch {}
    Start-Sleep -Milliseconds 300
}
throw "Monitor health check timed out."
