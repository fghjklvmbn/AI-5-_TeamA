[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath($PSScriptRoot)
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$RootEnv = Join-Path $Root ".env"
$Runtime = Join-Path $Root ".runtime"
$Logs = Join-Path $Runtime "logs"
$Secrets = Join-Path $Runtime "secrets"
$Gateway = Join-Path $Root "backend\gateway"
$Archive = Join-Path $Root "backend\archive_service"
$Frontend = Join-Path $Root "frontend"
$Admin = Join-Path $Root "admin"
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
$JwtSecretFromCaller = [Environment]::GetEnvironmentVariable("MEMORYPAL_JWT_SECRET", "Process")
$JwtSecretFileFromCaller = [Environment]::GetEnvironmentVariable("MEMORYPAL_JWT_SECRET_FILE", "Process")
$ModelSecretFromCaller = [Environment]::GetEnvironmentVariable("MEMORYPAL_MODEL_SERVICE_TOKEN", "Process")
$ModelSecretFileFromCaller = [Environment]::GetEnvironmentVariable("MEMORYPAL_MODEL_SERVICE_TOKEN_FILE", "Process")
$ArchiveSecretFromCaller = [Environment]::GetEnvironmentVariable("MEMORYPAL_ARCHIVE_SERVICE_TOKEN", "Process")
$ArchiveSecretFileFromCaller = [Environment]::GetEnvironmentVariable("MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE", "Process")
$StartedProcesses = New-Object 'System.Collections.Generic.List[object]'

function Register-StartedProcess(
    [string]$Name,
    [Diagnostics.Process]$Process,
    [string]$PidFile
) {
    $script:StartedProcesses.Add([PSCustomObject]@{
        Name = $Name
        Process = $Process
        PidFile = $PidFile
    })
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

function Stop-StartedProcessTree([Diagnostics.Process]$RootProcess) {
    $AllProcesses = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    $Tree = New-Object 'Collections.Generic.List[object]'
    $Pending = New-Object 'Collections.Generic.Queue[int]'
    $Seen = New-Object 'Collections.Generic.HashSet[int]'
    $Pending.Enqueue($RootProcess.Id)
    while ($Pending.Count -gt 0) {
        $ParentId = $Pending.Dequeue()
        if (-not $Seen.Add($ParentId)) { continue }
        $Current = $AllProcesses |
            Where-Object { $_.ProcessId -eq $ParentId } |
            Select-Object -First 1
        if ($null -ne $Current) { $Tree.Add($Current) }
        foreach ($Child in ($AllProcesses | Where-Object { $_.ParentProcessId -eq $ParentId })) {
            $Pending.Enqueue([int]$Child.ProcessId)
        }
    }
    $StopOrder = $Tree.ToArray()
    [array]::Reverse($StopOrder)
    if ($StopOrder.Count -eq 0 -and -not $RootProcess.HasExited) {
        Stop-ProcessAndVerify $RootProcess "rollback"
        return
    }
    foreach ($Item in $StopOrder) {
        $Process = Get-Process -Id $Item.ProcessId -ErrorAction SilentlyContinue
        if ($null -eq $Process) { continue }
        Stop-ProcessAndVerify $Process "rollback"
    }
}

function Stop-InvocationProcesses {
    if ($script:StartedProcesses.Count -eq 0) { return }
    Write-Host "Rolling back services started by this invocation..." -ForegroundColor Yellow
    for ($Index = $script:StartedProcesses.Count - 1; $Index -ge 0; $Index--) {
        $Entry = $script:StartedProcesses[$Index]
        try {
            Stop-StartedProcessTree $Entry.Process
            Write-Host "Rolled back $($Entry.Name)"
            if (Test-Path -LiteralPath $Entry.PidFile) {
                $TrackedText = [IO.File]::ReadAllText($Entry.PidFile).Trim()
                if ($TrackedText -eq [string]$Entry.Process.Id) {
                    Remove-Item -LiteralPath $Entry.PidFile -Force -ErrorAction Stop
                }
            }
        } catch {
            Write-Warning "Could not roll back $($Entry.Name): $($_.Exception.Message)"
        }
    }
}

function Import-DotEnv([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    foreach ($Line in [IO.File]::ReadAllLines($Path)) {
        $Value = $Line.Trim()
        if (-not $Value -or $Value.StartsWith("#") -or -not $Value.Contains("=")) { continue }
        $Pair = $Value.Split("=", 2)
        $Name = $Pair[0].Trim()
        $ParsedValue = $Pair[1].Trim()
        if ($ParsedValue.Length -ge 2) {
            $FirstQuote = $ParsedValue[0]
            $LastQuote = $ParsedValue[$ParsedValue.Length - 1]
            if (
                ($FirstQuote -eq '"' -and $LastQuote -eq '"') -or
                ($FirstQuote -eq "'" -and $LastQuote -eq "'")
            ) {
                $ParsedValue = $ParsedValue.Substring(1, $ParsedValue.Length - 2)
            }
        }
        if ([String]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($Name, "Process"))) {
            [Environment]::SetEnvironmentVariable($Name, $ParsedValue, "Process")
        }
    }
}

function Initialize-RuntimeSecret(
    [string]$VariableName,
    [string]$FileVariableName,
    [string]$DefaultPath,
    [string]$Label
) {
    $DirectValue = [Environment]::GetEnvironmentVariable($VariableName, "Process")
    if (-not [String]::IsNullOrWhiteSpace($DirectValue)) {
        $NormalizedDirect = $DirectValue.ToLowerInvariant().Replace('_', '-')
        if (
            $DirectValue.Length -lt 32 -or
            $NormalizedDirect.Contains("replace-with") -or
            $NormalizedDirect.Contains("placeholder") -or
            $NormalizedDirect.Contains("change-me") -or
            $NormalizedDirect.Contains("changeme")
        ) {
            throw "$Label secret must be at least 32 characters and must not be a placeholder."
        }
        [Environment]::SetEnvironmentVariable($FileVariableName, $null, "Process")
        return $DirectValue
    }

    $ConfiguredPath = [Environment]::GetEnvironmentVariable($FileVariableName, "Process")
    $UsesManagedPath = -not [String]::IsNullOrWhiteSpace($ConfiguredPath)
    if (-not $UsesManagedPath) {
        $SecretPath = $DefaultPath
    } elseif ([IO.Path]::IsPathRooted($ConfiguredPath)) {
        $SecretPath = [IO.Path]::GetFullPath($ConfiguredPath)
    } else {
        $SecretPath = [IO.Path]::GetFullPath((Join-Path $Root $ConfiguredPath))
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $SecretPath -Parent) | Out-Null
    $SecretValue = if (Test-Path -LiteralPath $SecretPath) {
        [IO.File]::ReadAllText($SecretPath).Trim()
    } else { "" }
    $NormalizedFileSecret = $SecretValue.ToLowerInvariant().Replace('_', '-')
    $FileSecretIsSafe = (
        $SecretValue.Length -ge 32 -and
        -not $NormalizedFileSecret.Contains("replace-with") -and
        -not $NormalizedFileSecret.Contains("placeholder") -and
        -not $NormalizedFileSecret.Contains("change-me") -and
        -not $NormalizedFileSecret.Contains("changeme")
    )
    if (-not $FileSecretIsSafe -and $UsesManagedPath) {
        throw "$Label secret file is missing, weak, or contains a placeholder: $SecretPath"
    }
    if (-not $FileSecretIsSafe) {
        $Bytes = New-Object byte[] 48
        $Generator = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $Generator.GetBytes($Bytes) } finally { $Generator.Dispose() }
        $SecretValue = [Convert]::ToBase64String($Bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
        [IO.File]::WriteAllText($SecretPath, $SecretValue, $Utf8NoBom)
    }
    [Environment]::SetEnvironmentVariable($FileVariableName, $null, "Process")
    [Environment]::SetEnvironmentVariable($VariableName, $SecretValue, "Process")
    return $SecretValue
}

function Resolve-SecretSource(
    [string]$VariableName,
    [string]$FileVariableName,
    [string]$CallerValue,
    [string]$CallerFile
) {
    $DirectValue = [Environment]::GetEnvironmentVariable($VariableName, "Process")
    $FileValue = [Environment]::GetEnvironmentVariable($FileVariableName, "Process")
    if ([String]::IsNullOrWhiteSpace($DirectValue) -or [String]::IsNullOrWhiteSpace($FileValue)) {
        return
    }
    if (
        -not [String]::IsNullOrWhiteSpace($CallerValue) -and
        [String]::IsNullOrWhiteSpace($CallerFile)
    ) {
        [Environment]::SetEnvironmentVariable($FileVariableName, $null, "Process")
        return
    }
    throw "$VariableName and $FileVariableName are both configured. Use exactly one secret source."
}

function Resolve-CondaPython([string]$EnvironmentName) {
    $Conda = Get-Command conda.exe -ErrorAction SilentlyContinue
    if ($null -eq $Conda) { $Conda = Get-Command conda -ErrorAction SilentlyContinue }
    if ($null -eq $Conda) { throw "Conda was not found: $EnvironmentName" }
    $EnvironmentPath = (& $Conda.Source env list --json | ConvertFrom-Json).envs | Where-Object {
        (Split-Path $_ -Leaf).Equals($EnvironmentName, [StringComparison]::OrdinalIgnoreCase)
    } | Select-Object -First 1
    if (-not $EnvironmentPath) { throw "Conda environment is missing: $EnvironmentName" }
    $EnvironmentPython = Join-Path $EnvironmentPath "python.exe"
    if (-not (Test-Path -LiteralPath $EnvironmentPython)) {
        throw "Python is missing from the Conda environment: $EnvironmentName"
    }
    return $EnvironmentPython
}

function Test-Http([string]$Uri) {
    try {
        $Response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 3
        return $Response.StatusCode -ge 200 -and $Response.StatusCode -lt 500
    } catch { return $false }
}

function Assert-AuthenticatedReady(
    [string]$Name,
    [string]$Uri,
    [string]$TokenVariableName = "MEMORYPAL_MODEL_SERVICE_TOKEN"
) {
    $Token = [Environment]::GetEnvironmentVariable($TokenVariableName, "Process")
    try {
        $Response = Invoke-WebRequest `
            -UseBasicParsing -Uri $Uri `
            -Headers @{ Authorization = "Bearer $Token" } -TimeoutSec 3
        if ($Response.StatusCode -ne 200) { throw "status $($Response.StatusCode)" }
    } catch {
        throw "$Name does not accept the configured model-service token."
    }
}

function Assert-RemoteDeploymentProfile(
    [string]$Name,
    [string]$Uri,
    [string]$ExpectedProfile,
    [string]$ExpectedBaseUrl,
    [string]$ExpectedApiUrl
) {
    try {
        $Response = Invoke-WebRequest `
            -UseBasicParsing -Uri "$Uri`?profile_check=$([guid]::NewGuid())" `
            -Headers @{ "Cache-Control" = "no-cache" } -TimeoutSec 3
        $Manifest = $Response.Content | ConvertFrom-Json
    } catch {
        throw "$Name port is occupied by a server without a valid deployment manifest."
    }
    if (
        [string]$Manifest.profile -cne $ExpectedProfile -or
        [string]$Manifest.baseUrl -cne $ExpectedBaseUrl -or
        [string]$Manifest.apiUrl -cne $ExpectedApiUrl
    ) {
        throw "$Name deployment mismatch: expected $ExpectedProfile at $ExpectedBaseUrl."
    }
}

function Wait-Http(
    [string]$Name,
    [string]$Uri,
    [Diagnostics.Process]$Process,
    [int]$Attempts = 60
) {
    for ($Attempt = 0; $Attempt -lt $Attempts; $Attempt++) {
        if ($Process.HasExited) { throw "$Name exited immediately after startup." }
        if (Test-Http $Uri) { return }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name health check timed out: $Uri"
}

function Assert-DeploymentProfile(
    [string]$Directory,
    [string]$ExpectedProfile,
    [string]$ExpectedBaseUrl,
    [string]$ExpectedApiUrl,
    [string]$Label
) {
    $IndexPath = Join-Path $Directory "index.html"
    $ManifestPath = Join-Path $Directory "deployment-profile.json"
    if (-not (Test-Path -LiteralPath $IndexPath) -or -not (Test-Path -LiteralPath $ManifestPath)) {
        throw "$Label build or deployment manifest is missing. Run install.cmd first."
    }
    try {
        $Manifest = [IO.File]::ReadAllText($ManifestPath) | ConvertFrom-Json
    } catch {
        throw "$Label deployment manifest is not valid JSON: $ManifestPath"
    }
    if (
        [string]$Manifest.profile -cne $ExpectedProfile -or
        [string]$Manifest.baseUrl -cne $ExpectedBaseUrl -or
        [string]$Manifest.apiUrl -cne $ExpectedApiUrl
    ) {
        throw "$Label build manifest mismatch: expected profile=$ExpectedProfile base=$ExpectedBaseUrl api=$ExpectedApiUrl"
    }
}

function Assert-PidSlotAvailable(
    [string]$Name,
    [string]$PidFile,
    [string]$FilePath,
    [string[]]$ArgumentList
) {
    if (-not (Test-Path -LiteralPath $PidFile)) { return }
    $TrackedId = 0
    if (-not [int]::TryParse(
        ([IO.File]::ReadAllText($PidFile).Trim()), [ref]$TrackedId
    )) {
        throw "$Name has an invalid PID file; refusing to start a duplicate service."
    }
    $Tracked = Get-CimInstance Win32_Process -ErrorAction Stop |
        Where-Object { $_.ProcessId -eq $TrackedId } |
        Select-Object -First 1
    if ($null -eq $Tracked) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction Stop
        return
    }

    $ExpectedExecutable = [IO.Path]::GetFullPath($FilePath)
    $TrackedExecutable = [string]$Tracked.ExecutablePath
    $TrackedCommand = [string]$Tracked.CommandLine
    $ExecutableMatches = (
        $TrackedExecutable.Equals($ExpectedExecutable, [StringComparison]::OrdinalIgnoreCase) -or
        $TrackedCommand.IndexOf($ExpectedExecutable, [StringComparison]::OrdinalIgnoreCase) -ge 0
    )
    $ArgumentsMatch = $true
    foreach ($Argument in $ArgumentList) {
        if (
            -not [String]::IsNullOrWhiteSpace($Argument) -and
            $TrackedCommand.IndexOf($Argument, [StringComparison]::OrdinalIgnoreCase) -lt 0
        ) {
            $ArgumentsMatch = $false
            break
        }
    }
    if ($ExecutableMatches -and $ArgumentsMatch) {
        throw "$Name PID $TrackedId is still running but unhealthy. Stop it explicitly before restarting."
    }

    Write-Warning "$Name PID $TrackedId belongs to another process; it will not be stopped."
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction Stop
}

function Start-ServiceProcess(
    [string]$Name,
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$WorkingDirectory,
    [string]$HealthUri,
    [int]$HealthAttempts = 60,
    [string]$ProfileUri = "",
    [string]$ExpectedProfile = "",
    [string]$ExpectedBaseUrl = "",
    [string]$ExpectedApiUrl = "",
    [string]$AuthenticatedReadyUri = "",
    [string]$AuthenticatedReadyTokenVariable = "MEMORYPAL_MODEL_SERVICE_TOKEN",
    [switch]$PublicProcess,
    [string[]]$AllowedMemoryPalVariables = @()
) {
    if (Test-Http $HealthUri) {
        if ($ProfileUri) {
            Assert-RemoteDeploymentProfile `
                $Name $ProfileUri $ExpectedProfile $ExpectedBaseUrl $ExpectedApiUrl
        }
        if ($AuthenticatedReadyUri) {
            Assert-AuthenticatedReady `
                $Name $AuthenticatedReadyUri $AuthenticatedReadyTokenVariable
        }
        Write-Host "$Name is already running: $HealthUri" -ForegroundColor Yellow
        return
    }
    $PidFile = Join-Path $Runtime "$Name.pid"
    Assert-PidSlotAvailable $Name $PidFile $FilePath $ArgumentList
    $QuotedArguments = $ArgumentList | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    }
    $StartInfo = New-Object Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $FilePath
    $StartInfo.Arguments = $QuotedArguments -join " "
    $StartInfo.WorkingDirectory = $WorkingDirectory
    $IsolatedEnvironment = $PublicProcess -or $AllowedMemoryPalVariables.Count -gt 0
    $StartInfo.UseShellExecute = -not $IsolatedEnvironment
    if ($IsolatedEnvironment) {
        $StartInfo.CreateNoWindow = $true
        $MemoryPalNames = @(
            $StartInfo.EnvironmentVariables.Keys |
                Where-Object { ([string]$_).StartsWith("MEMORYPAL_", [StringComparison]::OrdinalIgnoreCase) }
        )
        foreach ($VariableName in $MemoryPalNames) {
            if ($AllowedMemoryPalVariables -notcontains [string]$VariableName) {
                $StartInfo.EnvironmentVariables.Remove([string]$VariableName)
            }
        }
    } else {
        $StartInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    }
    Write-Host "Starting $Name`: $HealthUri"
    $Process = [Diagnostics.Process]::Start($StartInfo)
    Register-StartedProcess $Name $Process $PidFile
    [IO.File]::WriteAllText($PidFile, [string]$Process.Id)
    Wait-Http $Name $HealthUri $Process $HealthAttempts
    if ($ProfileUri) {
        Assert-RemoteDeploymentProfile `
            $Name $ProfileUri $ExpectedProfile $ExpectedBaseUrl $ExpectedApiUrl
    }
    if ($AuthenticatedReadyUri) {
        Assert-AuthenticatedReady `
            $Name $AuthenticatedReadyUri $AuthenticatedReadyTokenVariable
    }
    Write-Host "$Name started (PID $($Process.Id))" -ForegroundColor Green
}

try {
    if (-not (Test-Path -LiteralPath $RootEnv)) {
        throw "Root .env is missing. Run install.cmd first."
    }
    Import-DotEnv $RootEnv
    Resolve-SecretSource `
        "MEMORYPAL_JWT_SECRET" "MEMORYPAL_JWT_SECRET_FILE" `
        $JwtSecretFromCaller $JwtSecretFileFromCaller
    Resolve-SecretSource `
        "MEMORYPAL_MODEL_SERVICE_TOKEN" "MEMORYPAL_MODEL_SERVICE_TOKEN_FILE" `
        $ModelSecretFromCaller $ModelSecretFileFromCaller
    Resolve-SecretSource `
        "MEMORYPAL_ARCHIVE_SERVICE_TOKEN" "MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE" `
        $ArchiveSecretFromCaller $ArchiveSecretFileFromCaller
    Initialize-RuntimeSecret `
        "MEMORYPAL_JWT_SECRET" `
        "MEMORYPAL_JWT_SECRET_FILE" `
        (Join-Path $Secrets "jwt-secret") `
        "JWT" | Out-Null
    Initialize-RuntimeSecret `
        "MEMORYPAL_MODEL_SERVICE_TOKEN" `
        "MEMORYPAL_MODEL_SERVICE_TOKEN_FILE" `
        (Join-Path $Secrets "model-service-token") `
        "STT/TTS service" | Out-Null
    $LlmUrl = [Environment]::GetEnvironmentVariable("MEMORYPAL_LLM_URL", "Process")
    if ($LlmUrl -match '^https?://developark\.duckdns\.org/api_memoripal/llm(?:/|$)') {
        throw "The public LLM proxy is blocked. Set MEMORYPAL_LLM_URL to an internal URL."
    }
    $ArchiveToken = Initialize-RuntimeSecret `
        "MEMORYPAL_ARCHIVE_SERVICE_TOKEN" `
        "MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE" `
        (Join-Path $Secrets "archive-project3-service-token") `
        "Project3 Archive service"
    $Project3PublicApiUrl = [Environment]::GetEnvironmentVariable(
        "MEMORYPAL_PROJECT3_PUBLIC_API_URL", "Process"
    )
    if ([String]::IsNullOrWhiteSpace($Project3PublicApiUrl)) {
        $Project3PublicApiUrl = "https://developark.duckdns.org/api_memoripal/project3/gateway/v1"
    }
    $Project3PublicApiUrl = $Project3PublicApiUrl.TrimEnd('/')

    if (-not (Test-Path -LiteralPath $Python)) {
        throw "The Python virtual environment is missing. Run install.cmd first."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Frontend "node_modules"))) {
        throw "Project3 frontend packages are missing. Run install.cmd first."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Admin "node_modules"))) {
        throw "Project3 admin packages are missing. Run install.cmd first."
    }
    Assert-DeploymentProfile `
        (Join-Path $Frontend "dist-project3") `
        "project3" "/api_memoripal/project3/main" $Project3PublicApiUrl "Project3 Frontend"
    Assert-DeploymentProfile `
        (Join-Path $Admin "dist-project3") `
        "project3" "/api_memoripal/project3/manage/" $Project3PublicApiUrl "Project3 Admin"

    [Environment]::SetEnvironmentVariable("MEMORYPAL_ARCHIVE_SERVICE_TOKEN", $ArchiveToken, "Process")
    [Environment]::SetEnvironmentVariable("MEMORYPAL_DATABASE_PATH", (Join-Path $Gateway "data\memorypal.db"), "Process")
    # A single whitespace character keeps the process variable present so
    # python-dotenv cannot restore the main profile's URL; Settings strips it
    # back to the intentional empty value.
    [Environment]::SetEnvironmentVariable("MEMORYPAL_DATABASE_URL", " ", "Process")
    [Environment]::SetEnvironmentVariable("MEMORYPAL_TASK_QUEUE_MODE", "local", "Process")
    [Environment]::SetEnvironmentVariable("MEMORYPAL_REDIS_URL", " ", "Process")
    [Environment]::SetEnvironmentVariable("MEMORYPAL_REDIS_PREFIX", "memorypal-project3", "Process")
    [Environment]::SetEnvironmentVariable("MEMORYPAL_ROOT_PATH", "/api_memoripal/project3/gateway", "Process")
    [Environment]::SetEnvironmentVariable("MEMORYPAL_CORS_ORIGINS", "https://developark.duckdns.org,http://127.0.0.1:8083,http://127.0.0.1:8084", "Process")
    [Environment]::SetEnvironmentVariable("MEMORYPAL_STT_URL", "http://127.0.0.1:8001", "Process")
    [Environment]::SetEnvironmentVariable("MEMORYPAL_TTS_URL", "http://127.0.0.1:8003", "Process")
    [Environment]::SetEnvironmentVariable("MEMORYPAL_ARCHIVE_URL", "http://127.0.0.1:8006", "Process")
    [Environment]::SetEnvironmentVariable("MEMORYPAL_ARCHIVE_PRIVATE_UPLOAD_DIR", (Join-Path $Archive "private_voice_uploads"), "Process")
    [Environment]::SetEnvironmentVariable("MEMORYPAL_BUILD_PROFILE", "project3", "Process")
    [Environment]::SetEnvironmentVariable("MEMORYPAL_ADMIN_PORT", "8084", "Process")
    [Environment]::SetEnvironmentVariable("MEMORYPAL_ADMIN_DIST", "dist-project3", "Process")
    [Environment]::SetEnvironmentVariable("MEMORYPAL_ADMIN_BASE_URL", "/api_memoripal/project3/manage", "Process")
    New-Item -ItemType Directory -Force -Path $Logs | Out-Null

    $ArchivePython = Resolve-CondaPython "archive"
    Assert-AuthenticatedReady "STT" "http://127.0.0.1:8001/internal/ready"
    Assert-AuthenticatedReady "TTS" "http://127.0.0.1:8003/internal/ready"
    Write-Host "MemoryPal Project3 isolated startup" -ForegroundColor Cyan
    Write-Host "Shared internal services: STT 8001, TTS 8003, LLM"

    Start-ServiceProcess `
        -Name "archive-project3" `
        -FilePath $ArchivePython `
        -ArgumentList @("-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8006") `
        -WorkingDirectory $Archive `
        -HealthUri "http://127.0.0.1:8006/health" `
        -HealthAttempts 120 `
        -AuthenticatedReadyUri "http://127.0.0.1:8006/internal/ready" `
        -AuthenticatedReadyTokenVariable "MEMORYPAL_ARCHIVE_SERVICE_TOKEN" `
        -AllowedMemoryPalVariables @(
            "MEMORYPAL_ARCHIVE_DATABASE_URL",
            "MEMORYPAL_ARCHIVE_PENDING_TTL_SECONDS",
            "MEMORYPAL_ARCHIVE_PRIVATE_UPLOAD_DIR",
            "MEMORYPAL_ARCHIVE_PUBLIC_URL",
            "MEMORYPAL_ARCHIVE_REAPER_INTERVAL_SECONDS",
            "MEMORYPAL_ARCHIVE_SERVICE_TOKEN",
            "MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE",
            "MEMORYPAL_ARCHIVE_SQL_ECHO",
            "MEMORYPAL_DEFAULT_VOICE_ID"
        )

    Start-ServiceProcess `
        -Name "gateway-project3" `
        -FilePath $Python `
        -ArgumentList @(
            (Join-Path $Root "scripts\gateway_server.py"), "--host", "0.0.0.0", "--port", "8010",
            "--log-file", (Join-Path $Logs "gateway.log")
        ) `
        -WorkingDirectory $Gateway `
        -HealthUri "http://127.0.0.1:8010/v1/health" `
        -AuthenticatedReadyUri "http://127.0.0.1:8010/v1/internal/ready"

    Start-ServiceProcess `
        -Name "frontend-project3" `
        -FilePath $Python `
        -ArgumentList @(
            (Join-Path $Root "scripts\static_server.py"),
            "--directory", (Join-Path $Frontend "dist-project3"),
            "--host", "0.0.0.0", "--port", "8083",
            "--prefix", "/api_memoripal/project3/main",
            "--log-file", (Join-Path $Logs "frontend.log")
        ) `
        -WorkingDirectory $Root `
        -HealthUri "http://127.0.0.1:8083/" `
        -ProfileUri "http://127.0.0.1:8083/deployment-profile.json" `
        -ExpectedProfile "project3" `
        -ExpectedBaseUrl "/api_memoripal/project3/main" `
        -ExpectedApiUrl $Project3PublicApiUrl `
        -PublicProcess

    $Node = (Get-Command node.exe -ErrorAction Stop).Source
    Start-ServiceProcess `
        -Name "admin-project3" `
        -FilePath $Node `
        -ArgumentList @((Join-Path $Admin "server.mjs")) `
        -WorkingDirectory $Admin `
        -HealthUri "http://127.0.0.1:8084/" `
        -ProfileUri "http://127.0.0.1:8084/deployment-profile.json" `
        -ExpectedProfile "project3" `
        -ExpectedBaseUrl "/api_memoripal/project3/manage/" `
        -ExpectedApiUrl $Project3PublicApiUrl `
        -PublicProcess `
        -AllowedMemoryPalVariables @(
            "MEMORYPAL_ADMIN_PORT",
            "MEMORYPAL_BUILD_PROFILE",
            "MEMORYPAL_ADMIN_DIST",
            "MEMORYPAL_ADMIN_BASE_URL"
        )

    Write-Host "`nProject3 is running with isolated build artifacts and ports." -ForegroundColor Green
    Write-Host "Frontend : http://127.0.0.1:8083/api_memoripal/project3/main/"
    Write-Host "Gateway  : http://127.0.0.1:8010/v1/health"
    Write-Host "Admin    : http://127.0.0.1:8084/api_memoripal/project3/manage/"
    Write-Host "Archive  : http://127.0.0.1:8006/health"
    exit 0
} catch {
    $StartupError = $_.Exception.Message
    Stop-InvocationProcesses
    Write-Host "`nProject3 startup failed: $StartupError" -ForegroundColor Red
    Write-Host "Logs: $Logs"
    exit 1
}
