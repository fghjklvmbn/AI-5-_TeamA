[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$Runtime = Join-Path $Root ".runtime"

function Stop-MemoryPalProcess([string]$Name) {
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

    $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $ProcessInfo) {
        Remove-Item -LiteralPath $PidFile -Force
        Write-Host "$Name 프로세스는 이미 종료되었습니다." -ForegroundColor Yellow
        return
    }

    $CommandLine = [string]$ProcessInfo.CommandLine
    if ($CommandLine.IndexOf($Root, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw "$Name PID $ProcessId 는 현재 MemoryPal 프로젝트 프로세스가 아니므로 종료하지 않았습니다."
    }

    $Process = Get-Process -Id $ProcessId -ErrorAction Stop
    Stop-Process -Id $ProcessId
    if (-not $Process.WaitForExit(5000)) {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
        $Process.WaitForExit(5000) | Out-Null
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "$Name 종료 완료 (PID $ProcessId)" -ForegroundColor Green
}

try {
    Write-Host "MemoryPal Frontend + Gateway 통합 종료" -ForegroundColor Cyan
    Stop-MemoryPalProcess "frontend"
    Stop-MemoryPalProcess "gateway"
    Write-Host "`n모든 통합 실행 프로세스의 종료 처리가 완료되었습니다." -ForegroundColor Green
    Write-Host "로그는 $Runtime\logs 에 보존됩니다."
    exit 0
} catch {
    Write-Host "`n종료 실패: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
