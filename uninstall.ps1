[CmdletBinding()]
param(
    [switch]$RemoveData
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$Runtime = Join-Path $Root ".runtime"
$DatabasePath = Join-Path $Root "backend\gateway\data\memorypal.db"
$DatabaseBackup = $null

function Test-InProject([string]$Path) {
    $Resolved = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    return $Resolved -ne $Root -and $Resolved.StartsWith("$Root\", [StringComparison]::OrdinalIgnoreCase)
}

function Remove-ProjectPath([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    if (-not (Test-InProject $Path)) {
        throw "프로젝트 바깥 경로는 삭제할 수 없습니다: $Path"
    }
    $Resolved = [IO.Path]::GetFullPath($Path)
    Write-Host "삭제: $Resolved"
    Remove-Item -LiteralPath $Resolved -Recurse -Force
}

function Stop-TrackedProcess([string]$Name) {
    $PidFile = Join-Path $Runtime "$Name.pid"
    if (-not (Test-Path -LiteralPath $PidFile)) { return }
    $ProcessId = 0
    if (-not [int]::TryParse(([IO.File]::ReadAllText($PidFile).Trim()), [ref]$ProcessId)) {
        Remove-Item -LiteralPath $PidFile -Force
        return
    }
    $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $ProcessInfo) {
        Remove-Item -LiteralPath $PidFile -Force
        return
    }
    $CommandLine = [string]$ProcessInfo.CommandLine
    if ($CommandLine.IndexOf($Root, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        Write-Warning "$Name PID $ProcessId 는 현재 프로젝트 프로세스로 확인되지 않아 종료하지 않습니다."
        return
    }
    Stop-Process -Id $ProcessId -Force
    Write-Host "$Name 프로세스를 종료했습니다. (PID $ProcessId)"
}

try {
    Write-Host "MemoryPal 설치 파일과 캐시를 정리합니다." -ForegroundColor Cyan
    Stop-TrackedProcess "gateway"
    Stop-TrackedProcess "admin"
    Stop-TrackedProcess "frontend"

    if (-not $RemoveData -and (Test-Path -LiteralPath $DatabasePath)) {
        $DatabaseBackup = Join-Path ([IO.Path]::GetTempPath()) "memorypal-$([guid]::NewGuid()).db"
        Copy-Item -LiteralPath $DatabasePath -Destination $DatabaseBackup -Force
    }

    # Remove large dependency/build directories first so recursive cache discovery stays fast.
    foreach ($Path in @(
        (Join-Path $Root ".venv"),
        (Join-Path $Root "frontend\node_modules"),
        (Join-Path $Root "frontend\dist"),
        (Join-Path $Root "frontend\.expo"),
        (Join-Path $Root "admin\node_modules"),
        (Join-Path $Root "admin\dist"),
        (Join-Path $Root ".pytest_cache")
    )) {
        Remove-ProjectPath $Path
    }

    foreach ($SearchRoot in @((Join-Path $Root "backend"), (Join-Path $Root "scripts"))) {
        if (-not (Test-Path -LiteralPath $SearchRoot)) { continue }
        $Caches = Get-ChildItem -LiteralPath $SearchRoot -Directory -Recurse -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -in @("__pycache__", ".pytest_cache") } |
            Sort-Object { $_.FullName.Length } -Descending
        foreach ($Cache in $Caches) { Remove-ProjectPath $Cache.FullName }

        Get-ChildItem -LiteralPath $SearchRoot -File -Recurse -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in @(".pyc", ".pyo") } |
            ForEach-Object {
                if (Test-InProject $_.FullName) { Remove-Item -LiteralPath $_.FullName -Force }
            }
    }

    Get-ChildItem -LiteralPath (Join-Path $Root "backend\gateway") -Directory -Filter "*.egg-info" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-ProjectPath $_.FullName }

    if ($RemoveData) {
        Write-Warning "-RemoveData가 지정되어 로컬 사용자 데이터를 함께 삭제합니다."
        foreach ($Path in @(
            (Join-Path $Root "backend\gateway\data"),
            (Join-Path $Root "backend\archive_service\voice_uploads"),
            (Join-Path $Root "backend\TTS_Server\outputs")
        )) {
            Remove-ProjectPath $Path
        }
    } else {
        if ($DatabaseBackup -and -not (Test-Path -LiteralPath $DatabasePath)) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $DatabasePath) | Out-Null
            Copy-Item -LiteralPath $DatabaseBackup -Destination $DatabasePath -Force
        }
        if ($DatabaseBackup -and (Test-Path -LiteralPath $DatabaseBackup)) {
            Remove-Item -LiteralPath $DatabaseBackup -Force
        }
        Write-Host "Gateway SQLite DB, 업로드 파일, 루트 .env 설정은 보존했습니다." -ForegroundColor Green
    }

    Remove-ProjectPath $Runtime
    Write-Host "`n정리가 완료되었습니다." -ForegroundColor Green
    Write-Host "다시 설치하려면 install.cmd를 실행하세요."
    exit 0
} catch {
    Write-Host "`n정리 실패: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
