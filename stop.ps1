[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$Runtime = Join-Path $Root ".runtime"

function Stop-MemoryPalProcess(
    [string]$Name,
    [string]$ExpectedCommand
) {
    $PidFile = Join-Path $Runtime "$Name.pid"
    if (-not (Test-Path -LiteralPath $PidFile)) {
        Write-Host "$Name PID 파일이 없습니다. 이미 종료된 상태일 수 있습니다." -ForegroundColor Yellow
        return
    }

    $ProcessId = 0
    $PidText = [IO.File]::ReadAllText($PidFile).Trim()
    if (-not [int]::TryParse($PidText, [ref]$ProcessId)) {
        Remove-Item -LiteralPath $PidFile -Force
        Write-Warning "$Name PID 파일이 올바르지 않아 정리했습니다."
        return
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

    $CommandLine = [string]$ProcessInfo.CommandLine
    if ($CommandLine.IndexOf($ExpectedCommand, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
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
        $Tree.Add($Current)
        foreach ($Child in ($AllProcesses | Where-Object { $_.ParentProcessId -eq $ParentId })) {
            $Pending.Enqueue([int]$Child.ProcessId)
        }
    }

    foreach ($Item in $Tree) {
        $ItemCommand = [string]$Item.CommandLine
        $IsExpected = $ItemCommand.IndexOf(
            $ExpectedCommand, [StringComparison]::OrdinalIgnoreCase
        ) -ge 0
        $IsProjectChild = $ItemCommand.IndexOf(
            $Root, [StringComparison]::OrdinalIgnoreCase
        ) -ge 0
        if (-not $IsExpected -and -not $IsProjectChild) {
            throw "$Name 자식 PID $($Item.ProcessId)이 MemoryPal 프로세스로 확인되지 않아 종료하지 않습니다."
        }
    }

    $StopOrder = $Tree.ToArray()
    [array]::Reverse($StopOrder)
    foreach ($Item in $StopOrder) {
        $Process = Get-Process -Id $Item.ProcessId -ErrorAction SilentlyContinue
        if ($null -eq $Process) { continue }
        Stop-Process -Id $Item.ProcessId -ErrorAction SilentlyContinue
        if (-not $Process.WaitForExit(5000)) {
            Stop-Process -Id $Item.ProcessId -Force -ErrorAction SilentlyContinue
            $Process.WaitForExit(5000) | Out-Null
        }
    }

    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "$Name 종료 완료 (PID $ProcessId)" -ForegroundColor Green
}

try {
    Write-Host "MemoryPal 통합 서비스 종료" -ForegroundColor Cyan
    Stop-MemoryPalProcess "portrait-worker" "portrait_worker.py"
    Stop-MemoryPalProcess "admin" "admin\server.mjs"
    Stop-MemoryPalProcess "frontend" "static_server.py"
    Stop-MemoryPalProcess "gateway" "gateway_server.py"
    Stop-MemoryPalProcess "tts" "--port 8003"
    Stop-MemoryPalProcess "stt" "--port 8001"
    Stop-MemoryPalProcess "archive" "--port 8004"
    Write-Host "`n모든 통합 실행 프로세스의 종료 처리가 완료되었습니다." -ForegroundColor Green
    Write-Host "로그는 $Runtime\logs 에 보존됩니다."
    exit 0
} catch {
    Write-Host "`n종료 실패: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
