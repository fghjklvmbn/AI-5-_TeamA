[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath($PSScriptRoot)
$Runtime = Join-Path $Root ".runtime"
$Names = @(
    "admin-project3",
    "frontend-project3",
    "gateway-project3",
    "archive-project3"
)

foreach ($Name in $Names) {
    $PidFile = Join-Path $Runtime "$Name.pid"
    if (-not (Test-Path -LiteralPath $PidFile)) {
        Write-Host "$Name PID 파일 없음"
        continue
    }
    $ProcessId = [int][IO.File]::ReadAllText($PidFile)
    $Process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($Process) {
        & taskkill.exe /PID $ProcessId /T /F | Out-Null
        Write-Host "$Name 종료 완료"
    }
    Remove-Item -LiteralPath $PidFile -Force
}
