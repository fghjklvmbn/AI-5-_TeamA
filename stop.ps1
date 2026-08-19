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
    $ExecutableMatches = (
        -not [String]::IsNullOrWhiteSpace($ExpectedExecutableFragment) -and
        $ExecutablePath.IndexOf(
            $ExpectedExecutableFragment, [StringComparison]::OrdinalIgnoreCase
        ) -ge 0
    )
    return $IsProjectProcess -or $ExecutableMatches
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
        throw "$Name PID file is invalid; shared services will not be stopped."
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

function Stop-MemoryPalProcess(
    [string]$Name,
    [string]$ExpectedCommand,
    [string]$ExpectedExecutableFragment = ""
) {
    $PidFile = Join-Path $Runtime "$Name.pid"
    if (-not (Test-Path -LiteralPath $PidFile)) {
        Write-Host "$Name PID 파일이 없습니다. 이미 종료된 상태일 수 있습니다." -ForegroundColor Yellow
        return
    }

    $ProcessId = 0
    $PidText = [IO.File]::ReadAllText($PidFile).Trim()
    if (-not [int]::TryParse($PidText, [ref]$ProcessId)) {
        throw "$Name PID 파일이 올바르지 않습니다. 프로세스를 종료하거나 PID 파일을 삭제하지 않았습니다."
    }

    $AllProcesses = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    $ProcessInfo = $AllProcesses |
        Where-Object { $_.ProcessId -eq $ProcessId } |
        Select-Object -First 1
    if ($null -eq $ProcessInfo) {
        Remove-Item -LiteralPath $PidFile -Force
        Write-Host "$Name 프로세스가 이미 종료되었습니다." -ForegroundColor Yellow
        return
    }

    if (-not (Test-MemoryPalProcessInfo `
        $ProcessInfo $ExpectedCommand $ExpectedExecutableFragment
    )) {
        throw "$Name PID $ProcessId 이(가) 현재 MemoryPal 프로세스가 아니므로 종료하지 않습니다."
    }

    # A Windows virtual-environment launcher may keep the actual Python server
    # in a child process. Validate the full tree before stopping any process.
    $Tree = New-Object 'Collections.Generic.List[object]'
    $Pending = New-Object 'Collections.Generic.Queue[int]'
    $Pending.Enqueue($ProcessId)
    while ($Pending.Count -gt 0) {
        $ParentId = $Pending.Dequeue()
        $Current = $AllProcesses |
            Where-Object { $_.ProcessId -eq $ParentId } |
            Select-Object -First 1
        if ($null -eq $Current) { continue }
        # Windows attaches a console host to services started in a new window.
        # It is an OS helper rather than part of the MemoryPal command tree and
        # exits automatically when its owning service is stopped.
        if ($Current.Name -ieq "conhost.exe") { continue }
        $Tree.Add($Current)
        foreach ($Child in ($AllProcesses | Where-Object { $_.ParentProcessId -eq $ParentId })) {
            $Pending.Enqueue([int]$Child.ProcessId)
        }
    }

    foreach ($Item in $Tree) {
        if (-not (Test-MemoryPalProcessInfo `
            $Item $ExpectedCommand $ExpectedExecutableFragment
        )) {
            throw "$Name 자식 PID $($Item.ProcessId)이 MemoryPal 프로세스로 확인되지 않아 종료하지 않습니다."
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
    Write-Host "$Name 종료 완료 (PID $ProcessId)" -ForegroundColor Green
}

try {
    Write-Host "MemoryPal 통합 서비스 종료" -ForegroundColor Cyan
    $Project3UsesSharedModels = Test-TrackedMemoryPalProcess `
        "gateway-project3" "gateway_server.py"
    Stop-MemoryPalProcess "portrait-worker" "portrait_worker.py"
    Stop-MemoryPalProcess "admin" "admin\server.mjs"
    Stop-MemoryPalProcess "frontend" "static_server.py"
    Stop-MemoryPalProcess "gateway" "gateway_server.py"
    Stop-MemoryPalProcess "archive" "--port 8004" "\archive\python.exe"
    if ($Project3UsesSharedModels) {
        Write-Host "Project3 is running; shared STT/TTS services were left running." -ForegroundColor Yellow
    } else {
        Stop-MemoryPalProcess "tts" "--port 8003" "\qwen3-tts\python.exe"
        Stop-MemoryPalProcess "stt" "--port 8001" "\STT\python.exe"
    }
    Write-Host "`n모든 통합 실행 프로세스의 종료 처리가 완료되었습니다." -ForegroundColor Green
    Write-Host "로그는 $Runtime\logs 에 보존됩니다."
    exit 0
} catch {
    Write-Host "`n종료 실패: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
