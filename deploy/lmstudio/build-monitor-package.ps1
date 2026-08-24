[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$Stage = Join-Path $Root "dist\MemoryPal-LLM-Monitor"
$Archive = Join-Path $Root "dist\MemoryPal-LLM-Monitor.zip"
New-Item -ItemType Directory -Force -Path (Split-Path $Stage -Parent) | Out-Null
if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
if (Test-Path -LiteralPath $Archive) { Remove-Item -LiteralPath $Archive -Force }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null
Copy-Item -LiteralPath (Join-Path $Root "backend\monitor_agent\app.py") -Destination $Stage
Copy-Item -LiteralPath (Join-Path $Root "backend\monitor_agent\lmstudio_logs.py") -Destination $Stage
Copy-Item -LiteralPath (Join-Path $Root "backend\monitor_agent\server.py") -Destination $Stage
Copy-Item -LiteralPath (Join-Path $Root "backend\monitor_agent\requirements.txt") -Destination $Stage
Copy-Item -Path (Join-Path $Root "deploy\llm-monitor-package\*") -Destination $Stage -Recurse -Force
Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $Archive -CompressionLevel Optimal
Write-Host "Created $Archive" -ForegroundColor Green
