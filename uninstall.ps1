[CmdletBinding()]
param(
    [switch]$RemoveData
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$Runtime = Join-Path $Root ".runtime"

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

function Test-MemoryPalProcessInfo(
    [object]$ProcessInfo,
    [string]$ExpectedCommand,
    [string]$ExpectedExecutableFragment
) {
    $CommandLine = [string]$ProcessInfo.CommandLine
    $ExecutablePath = [string]$ProcessInfo.ExecutablePath
    $CommandMatches = (
        -not [String]::IsNullOrWhiteSpace($ExpectedCommand) -and
        $CommandLine.IndexOf($ExpectedCommand, [StringComparison]::OrdinalIgnoreCase) -ge 0
    )
    if (-not $CommandMatches) { return $false }

    $IsProjectProcess = (
        $CommandLine.IndexOf($Root, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
        $ExecutablePath.IndexOf($Root, [StringComparison]::OrdinalIgnoreCase) -ge 0
    )
    $ExternalExecutableMatches = (
        -not [String]::IsNullOrWhiteSpace($ExpectedExecutableFragment) -and
        $ExecutablePath.IndexOf(
            $ExpectedExecutableFragment, [StringComparison]::OrdinalIgnoreCase
        ) -ge 0
    )
    return $IsProjectProcess -or $ExternalExecutableMatches
}

function Stop-ProcessAndVerify(
    [Diagnostics.Process]$Process,
    [string]$Label
) {
    if ($Process.HasExited) { return }
    Stop-Process -InputObject $Process -ErrorAction Stop
    if (-not $Process.WaitForExit(5000)) {
        Stop-Process -InputObject $Process -Force -ErrorAction Stop
        if (-not $Process.WaitForExit(5000)) {
            throw "$Label PID $($Process.Id) did not exit after a forced stop."
        }
    }
    if (-not $Process.HasExited) {
        throw "$Label PID $($Process.Id) is still running after stop."
    }
}

function Stop-TrackedProcess(
    [string]$Name,
    [string]$ExpectedCommand,
    [string]$ExpectedExecutableFragment = ""
) {
    $PidFile = Join-Path $Runtime "$Name.pid"
    if (-not (Test-Path -LiteralPath $PidFile)) { return }
    $ProcessId = 0
    if (-not [int]::TryParse(([IO.File]::ReadAllText($PidFile).Trim()), [ref]$ProcessId)) {
        throw "$Name has an invalid PID file; uninstall stopped without deleting runtime state."
    }
    $AllProcesses = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    $ProcessInfo = $AllProcesses |
        Where-Object { $_.ProcessId -eq $ProcessId } |
        Select-Object -First 1
    if ($null -eq $ProcessInfo) {
        Remove-Item -LiteralPath $PidFile -Force
        return
    }
    if (-not (Test-MemoryPalProcessInfo `
        $ProcessInfo $ExpectedCommand $ExpectedExecutableFragment
    )) {
        throw "$Name PID $ProcessId is not the expected MemoryPal process. Uninstall stopped without deleting runtime state."
    }

    $Tree = New-Object 'Collections.Generic.List[object]'
    $Pending = New-Object 'Collections.Generic.Queue[int]'
    $Pending.Enqueue($ProcessId)
    while ($Pending.Count -gt 0) {
        $ParentId = $Pending.Dequeue()
        $Current = $AllProcesses |
            Where-Object { $_.ProcessId -eq $ParentId } |
            Select-Object -First 1
        if ($null -eq $Current) { continue }
        $Tree.Add($Current)
        foreach ($Child in ($AllProcesses | Where-Object { $_.ParentProcessId -eq $ParentId })) {
            $Pending.Enqueue([int]$Child.ProcessId)
        }
    }
    foreach ($Item in $Tree) {
        if (-not (Test-MemoryPalProcessInfo `
            $Item $ExpectedCommand $ExpectedExecutableFragment
        )) {
            throw "$Name child PID $($Item.ProcessId) is not an expected MemoryPal process."
        }
    }
    $StopOrder = $Tree.ToArray()
    [array]::Reverse($StopOrder)
    foreach ($Item in $StopOrder) {
        $Process = Get-Process -Id $Item.ProcessId -ErrorAction SilentlyContinue
        if ($null -eq $Process) { continue }
        Stop-ProcessAndVerify $Process $Name
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction Stop
    Write-Host "$Name 프로세스를 종료했습니다. (PID $ProcessId)"
}

try {
    Write-Host "MemoryPal 설치 파일과 캐시를 정리합니다." -ForegroundColor Cyan
    Stop-TrackedProcess "admin" "admin\server.mjs"
    Stop-TrackedProcess "frontend" "static_server.py"
    Stop-TrackedProcess "admin-project3" "admin\server.mjs"
    Stop-TrackedProcess "frontend-project3" "static_server.py"
    Stop-TrackedProcess "portrait-worker" "portrait_worker.py"
    Stop-TrackedProcess "gateway" "gateway_server.py"
    Stop-TrackedProcess "gateway-project3" "gateway_server.py"
    Stop-TrackedProcess "archive" "--port 8004" "\archive\python.exe"
    Stop-TrackedProcess "archive-project3" "--port 8006" "\archive\python.exe"
    Stop-TrackedProcess "tts" "--port 8003" "\qwen3-tts\python.exe"
    Stop-TrackedProcess "stt" "--port 8001" "\STT\python.exe"

    # Remove large dependency/build directories first so recursive cache discovery stays fast.
    foreach ($Path in @(
        (Join-Path $Root ".venv"),
        (Join-Path $Root "frontend\node_modules"),
        (Join-Path $Root "frontend\dist"),
        (Join-Path $Root "frontend\dist-main"),
        (Join-Path $Root "frontend\dist-project3"),
        (Join-Path $Root "frontend\.expo"),
        (Join-Path $Root "admin\node_modules"),
        (Join-Path $Root "admin\dist"),
        (Join-Path $Root "admin\dist-main"),
        (Join-Path $Root "admin\dist-project3"),
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
            (Join-Path $Root "backend\archive_service\private_voice_uploads"),
            (Join-Path $Root "backend\TTS_Server\outputs")
        )) {
            Remove-ProjectPath $Path
        }
    } else {
        Write-Host "Gateway SQLite DB, 업로드 파일, 루트 .env 설정은 보존했습니다." -ForegroundColor Green
    }

    if ($RemoveData) {
        Remove-ProjectPath $Runtime
    } else {
        Remove-ProjectPath (Join-Path $Runtime "logs")
        if (Test-Path -LiteralPath $Runtime) {
            Get-ChildItem -LiteralPath $Runtime -Filter "*.pid" -File -ErrorAction SilentlyContinue |
                ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
        }
        Write-Host "Runtime secrets were preserved with the local database." -ForegroundColor Green
    }
    Write-Host "`n정리가 완료되었습니다." -ForegroundColor Green
    Write-Host "다시 설치하려면 install.cmd를 실행하세요."
    exit 0
} catch {
    Write-Host "`n정리 실패: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
