[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$Runtime = Join-Path $Root ".runtime"

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

function Test-TrackedMemoryPalProcess(
    [string]$Name,
    [string]$ExpectedCommand,
    [string]$ExpectedExecutableFragment = ""
) {
    $PidFile = Join-Path $Runtime "$Name.pid"
    if (-not (Test-Path -LiteralPath $PidFile)) { return $false }
    $ProcessId = 0
    if (-not [int]::TryParse(
        ([IO.File]::ReadAllText($PidFile).Trim()), [ref]$ProcessId
    )) {
        throw "$Name has an invalid PID file; shared services will not be stopped."
    }
    $ProcessInfo = Get-CimInstance Win32_Process -ErrorAction Stop |
        Where-Object { $_.ProcessId -eq $ProcessId } |
        Select-Object -First 1
    if ($null -eq $ProcessInfo) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction Stop
        return $false
    }
    if (-not (Test-MemoryPalProcessInfo `
        $ProcessInfo $ExpectedCommand $ExpectedExecutableFragment
    )) {
        throw "$Name PID $ProcessId belongs to another process; shared services will not be stopped."
    }
    return $true
}

function Stop-TrackedProcess(
    [string]$Name,
    [string]$ExpectedCommand,
    [string]$ExpectedExecutableFragment = ""
) {
    $PidFile = Join-Path $Runtime "$Name.pid"
    if (-not (Test-Path -LiteralPath $PidFile)) {
        Write-Host "$Name is already stopped." -ForegroundColor Yellow
        return
    }

    $ProcessId = 0
    if (-not [int]::TryParse(
        ([IO.File]::ReadAllText($PidFile).Trim()), [ref]$ProcessId
    )) {
        throw "$Name has an invalid PID file; no process or tracking file was removed."
    }

    $AllProcesses = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    $RootProcess = $AllProcesses |
        Where-Object { $_.ProcessId -eq $ProcessId } |
        Select-Object -First 1
    if ($null -eq $RootProcess) {
        Remove-Item -LiteralPath $PidFile -Force
        Write-Host "$Name is already stopped." -ForegroundColor Yellow
        return
    }

    if (-not (Test-MemoryPalProcessInfo `
        $RootProcess $ExpectedCommand $ExpectedExecutableFragment
    )) {
        throw "$Name PID $ProcessId is not the expected MemoryPal process. Nothing was stopped."
    }

    # Validate the complete process tree before stopping any node. This avoids
    # killing an unrelated process after a stale PID file or PID reuse.
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
            throw "$Name child PID $($Item.ProcessId) is not an expected MemoryPal process. Nothing was stopped."
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
    Write-Host "$Name stopped (PID $ProcessId)." -ForegroundColor Green
}

try {
    Write-Host "Stopping MemoryPal Project3 services" -ForegroundColor Cyan
    $MainUsesSharedModels = Test-TrackedMemoryPalProcess "gateway" "gateway_server.py"
    Stop-TrackedProcess "admin-project3" "admin\server.mjs"
    Stop-TrackedProcess "frontend-project3" "static_server.py"
    Stop-TrackedProcess "gateway-project3" "gateway_server.py"
    Stop-TrackedProcess "archive-project3" "--port 8006" "\archive\python.exe"
    if ($MainUsesSharedModels) {
        Write-Host "Project3 is stopped. Main still uses the shared STT/TTS services." -ForegroundColor Green
    } else {
        Stop-TrackedProcess "tts" "--port 8003" "\qwen3-tts\python.exe"
        Stop-TrackedProcess "stt" "--port 8001" "\STT\python.exe"
        Write-Host "Project3 and the now-unused shared STT/TTS services are stopped." -ForegroundColor Green
    }
    exit 0
} catch {
    Write-Host "Project3 stop failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
