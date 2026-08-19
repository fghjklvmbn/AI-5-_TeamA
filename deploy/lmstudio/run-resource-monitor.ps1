[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TokenFile,
    [int]$Port = 8101
)

$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$PackageScript = Join-Path $Root "deploy\llm-monitor-package\start-monitor.ps1"
& $PackageScript -TokenFile $TokenFile -Port $Port
