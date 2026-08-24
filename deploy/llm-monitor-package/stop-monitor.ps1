[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = [IO.Path]::GetFullPath($PSScriptRoot)
$PidFile = Join-Path $Root "runtime\llm-monitor.pid"
if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Host "MemoryPal LLM monitor is not running."
    exit 0
}

$PidText = [IO.File]::ReadAllText($PidFile).Trim()
$MonitorPid = 0
if (-not [int]::TryParse($PidText, [ref]$MonitorPid)) {
    throw "Invalid monitor PID file: $PidFile"
}
$RootProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $MonitorPid" -ErrorAction SilentlyContinue
if ($null -eq $RootProcess) {
    Remove-Item -LiteralPath $PidFile -Force
    Write-Host "Removed stale monitor PID file."
    exit 0
}
$CommandLine = [string]$RootProcess.CommandLine
if (
    $CommandLine.IndexOf("server.py", [StringComparison]::OrdinalIgnoreCase) -lt 0 -or
    $CommandLine.IndexOf($Root, [StringComparison]::OrdinalIgnoreCase) -lt 0
) {
    throw "PID $MonitorPid does not belong to this MemoryPal monitor; refusing to stop it."
}

$All = @(Get-CimInstance Win32_Process)
$Pending = New-Object 'Collections.Generic.Queue[int]'
$Tree = New-Object 'Collections.Generic.List[int]'
$Pending.Enqueue($MonitorPid)
while ($Pending.Count -gt 0) {
    $Current = $Pending.Dequeue()
    $Tree.Add($Current)
    foreach ($Child in ($All | Where-Object { $_.ParentProcessId -eq $Current })) {
        $Pending.Enqueue([int]$Child.ProcessId)
    }
}
$Ids = $Tree.ToArray()
[array]::Reverse($Ids)
foreach ($Id in $Ids) {
    Stop-Process -Id $Id -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $PidFile -Force
Write-Host "MemoryPal LLM monitor stopped." -ForegroundColor Green
