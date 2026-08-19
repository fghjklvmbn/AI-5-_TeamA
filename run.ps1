[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath($PSScriptRoot)
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$Gateway = Join-Path $Root "backend\gateway"
$Stt = Join-Path $Root "backend\STT_backend_server"
$Tts = Join-Path $Root "backend\TTS_Server"
$Archive = Join-Path $Root "backend\archive_service"
$Frontend = Join-Path $Root "frontend"
$Admin = Join-Path $Root "admin"
$RootEnv = Join-Path $Root ".env"
$Runtime = Join-Path $Root ".runtime"
$Logs = Join-Path $Runtime "logs"
$Secrets = Join-Path $Runtime "secrets"
$ArchiveServiceTokenFile = Join-Path $Secrets "archive-service-token"
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
    foreach ($Line in [IO.File]::ReadAllLines($Path)) {
        $Value = $Line.Trim()
        if (-not $Value -or $Value.StartsWith("#") -or -not $Value.Contains("=")) { continue }
        $Pair = $Value.Split('=', 2)
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
        # Values injected by a service manager or secret store take precedence
        # over the developer-friendly root .env file.
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
            throw "$Label 비밀키는 예시값이 아닌 32자 이상의 값이어야 합니다."
        }
        [Environment]::SetEnvironmentVariable($FileVariableName, $null, "Process")
        Write-Host "$Label 비밀키: 프로세스/비밀 저장소 값 사용"
        return
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
        $SecretBytes = New-Object byte[] 48
        $Random = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $Random.GetBytes($SecretBytes) } finally { $Random.Dispose() }
        $SecretValue = [Convert]::ToBase64String($SecretBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
        [IO.File]::WriteAllText($SecretPath, $SecretValue, $Utf8NoBom)
        Write-Host "$Label 비밀키: ignored runtime 저장소에 생성"
    } else {
        Write-Host "$Label 비밀키: ignored runtime 저장소에서 재사용"
    }

    # Gateway, STT and TTS are child processes. They receive the secret only in
    # memory, while the durable copy stays outside .env and source control.
    [Environment]::SetEnvironmentVariable($FileVariableName, $null, "Process")
    [Environment]::SetEnvironmentVariable($VariableName, $SecretValue, "Process")
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
        # The direct deployment secret is authoritative; the file setting came
        # from the local .env template and must not create an ambiguous source.
        [Environment]::SetEnvironmentVariable($FileVariableName, $null, "Process")
        return
    }
    throw "$VariableName and $FileVariableName are both configured. Run install.cmd to migrate legacy inline secrets or configure exactly one source."
}

function Resolve-CondaPython([string]$EnvironmentName) {
    $Conda = Get-Command conda.exe -ErrorAction SilentlyContinue
    if ($null -eq $Conda) {
        $Conda = Get-Command conda -ErrorAction SilentlyContinue
    }
    if ($null -eq $Conda) {
        throw "Conda를 찾을 수 없습니다. $EnvironmentName 환경을 먼저 준비해 주세요."
    }

    $EnvironmentList = (& $Conda.Source env list --json | ConvertFrom-Json).envs
    $EnvironmentPath = $EnvironmentList | Where-Object {
        (Split-Path $_ -Leaf).Equals($EnvironmentName, [StringComparison]::OrdinalIgnoreCase)
    } | Select-Object -First 1
    if (-not $EnvironmentPath) {
        throw "Conda $EnvironmentName 환경이 없습니다. 해당 음성 서버 환경을 먼저 설치해 주세요."
    }

    $Python = Join-Path $EnvironmentPath "python.exe"
    if (-not (Test-Path -LiteralPath $Python)) {
        throw "Conda $EnvironmentName 환경의 Python을 찾을 수 없습니다: $Python"
    }
    return $Python
}

function Test-Http([string]$Uri) {
    try {
        $Response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2
        return $Response.StatusCode -ge 200 -and $Response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Assert-AuthenticatedReady(
    [string]$Name,
    [string]$Uri,
    [string]$TokenVariableName = "MEMORYPAL_MODEL_SERVICE_TOKEN"
) {
    $Token = [Environment]::GetEnvironmentVariable($TokenVariableName, "Process")
    try {
        $Response = Invoke-WebRequest `
            -UseBasicParsing `
            -Uri $Uri `
            -Headers @{ Authorization = "Bearer $Token" } `
            -TimeoutSec 3
        if ($Response.StatusCode -ne 200) { throw "status $($Response.StatusCode)" }
    } catch {
        throw "$Name is running with a different model-service token or is not a MemoryPal service. Stop the tracked services before restarting."
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
            -UseBasicParsing `
            -Uri "$Uri`?profile_check=$([guid]::NewGuid())" `
            -Headers @{ "Cache-Control" = "no-cache" } `
            -TimeoutSec 3
        $Manifest = $Response.Content | ConvertFrom-Json
    } catch {
        throw "$Name port is occupied by a server without a valid deployment manifest: $Uri"
    }
    if (
        [string]$Manifest.profile -cne $ExpectedProfile -or
        [string]$Manifest.baseUrl -cne $ExpectedBaseUrl -or
        [string]$Manifest.apiUrl -cne $ExpectedApiUrl
    ) {
        throw "$Name deployment mismatch: expected $ExpectedProfile at $ExpectedBaseUrl. Stop the old process before restarting."
    }
}

function Wait-Http(
    [string]$Name,
    [string]$Uri,
    [Diagnostics.Process]$Process,
    [int]$Attempts = 30
) {
    for ($Attempt = 0; $Attempt -lt $Attempts; $Attempt++) {
        if ($Process.HasExited) {
            throw "$Name 프로세스가 시작 직후 종료되었습니다. 로그를 확인해 주세요."
        }
        if (Test-Http $Uri) { return }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name 상태 확인 시간이 초과되었습니다: $Uri"
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
        throw "$Label 빌드 또는 deployment-profile.json이 없습니다. 먼저 install.cmd를 실행해 주세요."
    }
    try {
        $Manifest = [IO.File]::ReadAllText($ManifestPath) | ConvertFrom-Json
    } catch {
        throw "$Label 배포 프로필 파일이 올바른 JSON이 아닙니다: $ManifestPath"
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
        throw "$Name PID file is invalid; refusing to start a potentially duplicate service."
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
        throw "$Name PID $TrackedId is still running but failed its health check. Stop it explicitly before restarting."
    }

    Write-Warning "$Name PID $TrackedId belongs to another process; it will not be stopped."
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction Stop
}

function Start-MemoryPalProcess(
    [string]$Name,
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$WorkingDirectory,
    [string]$PidFile,
    [string]$HealthUri,
    [int]$HealthAttempts = 30,
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
        Write-Host "$Name 서비스가 이미 실행 중입니다: $HealthUri" -ForegroundColor Yellow
        return
    }

    Assert-PidSlotAvailable $Name $PidFile $FilePath $ArgumentList
    $QuotedArguments = $ArgumentList | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    }
    $StartInfo = New-Object Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $FilePath
    $StartInfo.Arguments = $QuotedArguments -join ' '
    $StartInfo.WorkingDirectory = $WorkingDirectory
    $IsolatedEnvironment = $PublicProcess -or $AllowedMemoryPalVariables.Count -gt 0
    $StartInfo.UseShellExecute = -not $IsolatedEnvironment
    if ($IsolatedEnvironment) {
        $StartInfo.CreateNoWindow = $true
        # Each isolated child receives only the MemoryPal settings it needs.
        # Other OS/GPU/runtime variables remain available.
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
    Write-Host "$Name 서비스를 시작합니다: $HealthUri"
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
    Write-Host "$Name 시작 완료 (PID $($Process.Id))" -ForegroundColor Green
}

function Start-MemoryPalBackgroundProcess(
    [string]$Name,
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$WorkingDirectory,
    [string]$PidFile
) {
    if (Test-Path -LiteralPath $PidFile) {
        $ExistingId = 0
        $ExistingText = [IO.File]::ReadAllText($PidFile).Trim()
        if (-not [int]::TryParse($ExistingText, [ref]$ExistingId)) {
            throw "$Name PID file is invalid; refusing to start a duplicate worker: $PidFile"
        }
        $ExistingInfo = Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object { $_.ProcessId -eq $ExistingId } |
            Select-Object -First 1
        if ($null -ne $ExistingInfo) {
            $ExistingCommand = [string]$ExistingInfo.CommandLine
            $ExistingExecutable = [string]$ExistingInfo.ExecutablePath
            $IsExpectedWorker = (
                $ExistingCommand.IndexOf(
                    "portrait_worker.py", [StringComparison]::OrdinalIgnoreCase
                ) -ge 0 -and
                (
                    $ExistingCommand.IndexOf($Root, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
                    $ExistingExecutable.IndexOf($Root, [StringComparison]::OrdinalIgnoreCase) -ge 0
                )
            )
            if ($IsExpectedWorker) {
                Write-Host "$Name 서비스가 이미 실행 중입니다 (PID $ExistingId)" -ForegroundColor Yellow
                return
            }
            Write-Warning "$Name PID $ExistingId belongs to another process; it will not be stopped."
        }
        Remove-Item -LiteralPath $PidFile -Force
    }
    $QuotedArguments = $ArgumentList | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    }
    $StartInfo = New-Object Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $FilePath
    $StartInfo.Arguments = $QuotedArguments -join ' '
    $StartInfo.WorkingDirectory = $WorkingDirectory
    $StartInfo.UseShellExecute = $true
    $StartInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    Write-Host "$Name 백그라운드 서비스를 시작합니다."
    $Process = [Diagnostics.Process]::Start($StartInfo)
    Register-StartedProcess $Name $Process $PidFile
    [IO.File]::WriteAllText($PidFile, [string]$Process.Id)
    Start-Sleep -Milliseconds 1200
    if ($Process.HasExited) {
        throw "$Name 프로세스가 시작 직후 종료되었습니다. 로그를 확인해 주세요."
    }
    Write-Host "$Name 시작 완료 (PID $($Process.Id))" -ForegroundColor Green
}

try {
    if (-not (Test-Path -LiteralPath $RootEnv)) {
        throw "루트 .env가 없습니다. 먼저 install.cmd를 실행해 주세요."
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
        "JWT"
    Initialize-RuntimeSecret `
        "MEMORYPAL_MODEL_SERVICE_TOKEN" `
        "MEMORYPAL_MODEL_SERVICE_TOKEN_FILE" `
        (Join-Path $Secrets "model-service-token") `
        "STT/TTS 서비스"
    Initialize-RuntimeSecret `
        "MEMORYPAL_ARCHIVE_SERVICE_TOKEN" `
        "MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE" `
        $ArchiveServiceTokenFile `
        "Archive service"
    $MainPublicApiUrl = [Environment]::GetEnvironmentVariable(
        "MEMORYPAL_MAIN_PUBLIC_API_URL", "Process"
    )
    if ([String]::IsNullOrWhiteSpace($MainPublicApiUrl)) {
        $MainPublicApiUrl = [Environment]::GetEnvironmentVariable(
            "EXPO_PUBLIC_API_URL", "Process"
        )
    }
    if ([String]::IsNullOrWhiteSpace($MainPublicApiUrl)) {
        $MainPublicApiUrl = "https://developark.duckdns.org/api_memoripal/gateway/v1"
    }
    $MainPublicApiUrl = $MainPublicApiUrl.TrimEnd('/')
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        throw "Python 가상환경이 없습니다. 먼저 install.cmd를 실행해 주세요."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Frontend "node_modules"))) {
        throw "Frontend 패키지가 없습니다. 먼저 install.cmd를 실행해 주세요."
    }
    Assert-DeploymentProfile `
        (Join-Path $Frontend "dist-main") `
        "main" "/api_memoripal/main" $MainPublicApiUrl "Frontend"
    if (-not (Test-Path -LiteralPath (Join-Path $Admin "node_modules"))) {
        throw "관리자 페이지 패키지가 없습니다. 먼저 install.cmd를 실행해 주세요."
    }
    Assert-DeploymentProfile `
        (Join-Path $Admin "dist-main") `
        "main" "/api_memoripal/manage/" $MainPublicApiUrl "관리자 페이지"
    $NodeCommand = Get-Command node.exe -ErrorAction Stop
    [Environment]::SetEnvironmentVariable("MEMORYPAL_ADMIN_PORT", "8082", "Process")
    [Environment]::SetEnvironmentVariable("MEMORYPAL_BUILD_PROFILE", "main", "Process")
    [Environment]::SetEnvironmentVariable("MEMORYPAL_ADMIN_DIST", "dist-main", "Process")
    [Environment]::SetEnvironmentVariable("MEMORYPAL_ADMIN_BASE_URL", "/api_memoripal/manage", "Process")
    New-Item -ItemType Directory -Force -Path $Logs | Out-Null

    $SttPython = Resolve-CondaPython "STT"
    $TtsPython = Resolve-CondaPython "qwen3-tts"
    $ArchivePython = Resolve-CondaPython "archive"

    Write-Host "MemoryPal Frontend + Backend 통합 실행" -ForegroundColor Cyan

    # Bring up authenticated internal dependencies before exposing Gateway or
    # either static UI. A failed model/archive readiness check therefore rolls
    # back without leaving a partially usable public deployment.
    Start-MemoryPalProcess `
        -Name "archive" `
        -FilePath $ArchivePython `
        -ArgumentList @("-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8004") `
        -WorkingDirectory $Archive `
        -PidFile (Join-Path $Runtime "archive.pid") `
        -HealthUri "http://127.0.0.1:8004/health" `
        -HealthAttempts 120 `
        -AuthenticatedReadyUri "http://127.0.0.1:8004/internal/ready" `
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

    Start-MemoryPalProcess `
        -Name "stt" `
        -FilePath $SttPython `
        -ArgumentList @("-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001") `
        -WorkingDirectory $Stt `
        -PidFile (Join-Path $Runtime "stt.pid") `
        -HealthUri "http://127.0.0.1:8001/health" `
        -HealthAttempts 120 `
        -AuthenticatedReadyUri "http://127.0.0.1:8001/internal/ready" `
        -AllowedMemoryPalVariables @("MEMORYPAL_MODEL_SERVICE_TOKEN")

    Start-MemoryPalProcess `
        -Name "tts" `
        -FilePath $TtsPython `
        -ArgumentList @("-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8003") `
        -WorkingDirectory $Tts `
        -PidFile (Join-Path $Runtime "tts.pid") `
        -HealthUri "http://127.0.0.1:8003/health" `
        -HealthAttempts 600 `
        -AuthenticatedReadyUri "http://127.0.0.1:8003/internal/ready" `
        -AllowedMemoryPalVariables @(
            "MEMORYPAL_MODEL_SERVICE_TOKEN",
            "MEMORYPAL_TTS_ENGINE",
            "MEMORYPAL_TTS_PUBLIC_URL",
            "MEMORYPAL_TTS_REFERENCE_AUDIO_ROOTS",
            "MEMORYPAL_TTS_REFERENCE_UPLOAD_DIR"
        )

    Start-MemoryPalProcess `
        -Name "gateway" `
        -FilePath $VenvPython `
        -ArgumentList @(
            (Join-Path $Root "scripts\gateway_server.py"), "--host", "0.0.0.0", "--port", "8010",
            "--log-file", (Join-Path $Logs "gateway.log")
        ) `
        -WorkingDirectory $Gateway `
        -PidFile (Join-Path $Runtime "gateway.pid") `
        -HealthUri "http://127.0.0.1:8010/v1/health" `
        -AuthenticatedReadyUri "http://127.0.0.1:8010/v1/internal/ready"

    $MonitorServer = Join-Path $Root "backend\monitor_agent\server.py"
    $MonitorDefinitions = @(
        @{ Name = "stt"; Port = "8100"; TargetPid = [IO.File]::ReadAllText((Join-Path $Runtime "stt.pid")).Trim(); Health = "http://127.0.0.1:8001/health" },
        @{ Name = "tts"; Port = "8102"; TargetPid = [IO.File]::ReadAllText((Join-Path $Runtime "tts.pid")).Trim(); Health = "http://127.0.0.1:8003/health" },
        @{ Name = "gateway"; Port = "8103"; TargetPid = [IO.File]::ReadAllText((Join-Path $Runtime "gateway.pid")).Trim(); Health = "http://127.0.0.1:8010/v1/health" },
        @{ Name = "archive"; Port = "8104"; TargetPid = [IO.File]::ReadAllText((Join-Path $Runtime "archive.pid")).Trim(); Health = "http://127.0.0.1:8004/health" }
    )
    foreach ($Monitor in $MonitorDefinitions) {
        Start-MemoryPalProcess `
            -Name "monitor-$($Monitor.Name)" `
            -FilePath $VenvPython `
            -ArgumentList @(
                $MonitorServer,
                "--service", $Monitor.Name,
                "--host", "0.0.0.0",
                "--port", $Monitor.Port,
                "--target-pid", $Monitor.TargetPid,
                "--health-url", $Monitor.Health,
                "--log-path", (Join-Path $Logs "$($Monitor.Name).hardware.jsonl")
            ) `
            -WorkingDirectory (Join-Path $Root "backend\monitor_agent") `
            -PidFile (Join-Path $Runtime "monitor-$($Monitor.Name).pid") `
            -HealthUri "http://127.0.0.1:$($Monitor.Port)/health" `
            -AllowedMemoryPalVariables @(
                "MEMORYPAL_MODEL_SERVICE_TOKEN",
                "MEMORYPAL_MODEL_SERVICE_TOKEN_FILE",
                "MEMORYPAL_MONITOR_INTERVAL_SECONDS"
            )
    }

    $TaskQueueMode = [Environment]::GetEnvironmentVariable(
        "MEMORYPAL_TASK_QUEUE_MODE", "Process"
    )
    if ($TaskQueueMode -and $TaskQueueMode.Equals("redis", [StringComparison]::OrdinalIgnoreCase)) {
        Start-MemoryPalBackgroundProcess `
            -Name "portrait-worker" `
            -FilePath $VenvPython `
            -ArgumentList @(
                (Join-Path $Root "scripts\portrait_worker.py"),
                "--log-file", (Join-Path $Logs "portrait-worker.log")
            ) `
            -WorkingDirectory $Gateway `
            -PidFile (Join-Path $Runtime "portrait-worker.pid")
    }

    Start-MemoryPalProcess `
        -Name "frontend" `
        -FilePath $VenvPython `
        -ArgumentList @(
            (Join-Path $Root "scripts\static_server.py"),
            "--directory", (Join-Path $Frontend "dist-main"),
            "--host", "0.0.0.0",
            "--port", "8081",
            "--prefix", "/api_memoripal/main",
            "--log-file", (Join-Path $Logs "frontend.log")
        ) `
        -WorkingDirectory $Root `
        -PidFile (Join-Path $Runtime "frontend.pid") `
        -HealthUri "http://127.0.0.1:8081/" `
        -ProfileUri "http://127.0.0.1:8081/deployment-profile.json" `
        -ExpectedProfile "main" `
        -ExpectedBaseUrl "/api_memoripal/main" `
        -ExpectedApiUrl $MainPublicApiUrl `
        -PublicProcess

    Start-MemoryPalProcess `
        -Name "admin" `
        -FilePath $NodeCommand.Source `
        -ArgumentList @((Join-Path $Admin "server.mjs")) `
        -WorkingDirectory $Admin `
        -PidFile (Join-Path $Runtime "admin.pid") `
        -HealthUri "http://127.0.0.1:8082/" `
        -ProfileUri "http://127.0.0.1:8082/deployment-profile.json" `
        -ExpectedProfile "main" `
        -ExpectedBaseUrl "/api_memoripal/manage/" `
        -ExpectedApiUrl $MainPublicApiUrl `
        -PublicProcess `
        -AllowedMemoryPalVariables @(
            "MEMORYPAL_ADMIN_PORT",
            "MEMORYPAL_BUILD_PROFILE",
            "MEMORYPAL_ADMIN_DIST",
            "MEMORYPAL_ADMIN_BASE_URL"
        )

    Write-Host "`n모든 애플리케이션 서비스가 실행 중입니다." -ForegroundColor Green
    Write-Host "Frontend : http://127.0.0.1:8081/"
    Write-Host "Admin    : http://127.0.0.1:8082/"
    Write-Host "Gateway  : http://127.0.0.1:8010/v1/health"
    Write-Host "STT      : http://127.0.0.1:8001/health"
    Write-Host "TTS      : http://127.0.0.1:8003/docs"
    Write-Host "Archive  : http://127.0.0.1:8004/health"
    Write-Host "Monitors : STT 8100 / LLM 8101(remote) / TTS 8102 / Gateway 8103 / Archive 8104"
    Write-Host "API Docs : http://127.0.0.1:8010/docs"
    Write-Host "Logs     : $Logs"
    Write-Host "External : https://developark.duckdns.org/api_memoripal/manage/"
    if ($TaskQueueMode -and $TaskQueueMode.Equals("redis", [StringComparison]::OrdinalIgnoreCase)) {
        Write-Host "Worker   : Redis 분산 자화상 워커 실행 중"
    }
    Write-Host "`nLLM은 프로젝트 루트 .env 설정을 사용합니다."
    exit 0
} catch {
    $StartupError = $_.Exception.Message
    Stop-InvocationProcesses
    Write-Host "`n실행 실패: $StartupError" -ForegroundColor Red
    Write-Host "로그 위치: $Logs"
    exit 1
}
