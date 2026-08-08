[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath($PSScriptRoot)
$Venv = Join-Path $Root ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$Gateway = Join-Path $Root "backend\gateway"
$Frontend = Join-Path $Root "frontend"
$Admin = Join-Path $Root "admin"
$RootEnv = Join-Path $Root ".env"
$Runtime = Join-Path $Root ".runtime"
$Secrets = Join-Path $Runtime "secrets"
$Utf8NoBom = [Text.UTF8Encoding]::new($false)
$JwtSecretFromCaller = [Environment]::GetEnvironmentVariable("MEMORYPAL_JWT_SECRET", "Process")
$JwtSecretFileFromCaller = [Environment]::GetEnvironmentVariable("MEMORYPAL_JWT_SECRET_FILE", "Process")
$ModelSecretFromCaller = [Environment]::GetEnvironmentVariable("MEMORYPAL_MODEL_SERVICE_TOKEN", "Process")
$ModelSecretFileFromCaller = [Environment]::GetEnvironmentVariable("MEMORYPAL_MODEL_SERVICE_TOKEN_FILE", "Process")
$ArchiveSecretFromCaller = [Environment]::GetEnvironmentVariable("MEMORYPAL_ARCHIVE_SERVICE_TOKEN", "Process")
$ArchiveSecretFileFromCaller = [Environment]::GetEnvironmentVariable("MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE", "Process")

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Assert-LastExit([string]$Action) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Action 실패 (종료 코드: $LASTEXITCODE)"
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
        if ([String]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($Name, "Process"))) {
            [Environment]::SetEnvironmentVariable($Name, $ParsedValue, "Process")
        }
    }
}

function Test-UsableSecret([string]$Value) {
    if ([String]::IsNullOrWhiteSpace($Value) -or $Value.Length -lt 32) { return $false }
    $Normalized = $Value.ToLowerInvariant().Replace('_', '-')
    return -not (
        $Normalized.Contains("replace-with") -or
        $Normalized.Contains("placeholder") -or
        $Normalized.Contains("change-me") -or
        $Normalized.Contains("changeme")
    )
}

function Get-DotEnvValue([string]$Content, [string]$Name) {
    # In .NET multiline mode, `$` matches before `\n` but not before the
    # preceding `\r`. This lookahead supports LF, CRLF, and a final line with
    # no terminator without consuming or changing the original line ending.
    $Pattern = "(?m)^" + [Text.RegularExpressions.Regex]::Escape($Name) + "=(?<value>[^\r\n]*)(?=\r?$)"
    $Match = [Text.RegularExpressions.Regex]::Match($Content, $Pattern)
    if (-not $Match.Success) { return "" }
    $ParsedValue = $Match.Groups["value"].Value.Trim()
    if ($ParsedValue.Length -ge 2) {
        $FirstQuote = $ParsedValue[0]
        $LastQuote = $ParsedValue[$ParsedValue.Length - 1]
        if (
            ($FirstQuote -eq '"' -and $LastQuote -eq '"') -or
            ($FirstQuote -eq "'" -and $LastQuote -eq "'")
        ) {
            return $ParsedValue.Substring(1, $ParsedValue.Length - 2)
        }
    }
    return $ParsedValue
}

function Write-SecretFile([string]$Path, [string]$Value) {
    $Parent = Split-Path $Path -Parent
    New-Item -ItemType Directory -Force -Path $Parent | Out-Null
    $Temporary = Join-Path $Parent (".{0}.{1}.tmp" -f (Split-Path $Path -Leaf), [guid]::NewGuid())
    $Backup = "$Temporary.bak"
    try {
        [IO.File]::WriteAllText($Temporary, $Value, $Utf8NoBom)
        if (Test-Path -LiteralPath $Path) {
            [IO.File]::Replace($Temporary, $Path, $Backup, $true)
        } else {
            [IO.File]::Move($Temporary, $Path)
        }
    } finally {
        Remove-Item -LiteralPath $Temporary -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $Backup -Force -ErrorAction SilentlyContinue
    }
}

function Initialize-SecretFile([string]$Path, [string]$Label, [string]$Seed = "") {
    New-Item -ItemType Directory -Force -Path (Split-Path $Path -Parent) | Out-Null
    $Existing = if (Test-Path -LiteralPath $Path) {
        [IO.File]::ReadAllText($Path).Trim()
    } else { "" }
    if (Test-UsableSecret $Seed) {
        if ($Existing -ne $Seed) { Write-SecretFile $Path $Seed }
        Write-Host "$Label secret: migrated from the existing configuration"
        return
    }
    if (Test-UsableSecret $Existing) {
        Write-Host "$Label 비밀키: 기존 runtime secret 재사용"
        return
    }
    $Bytes = New-Object byte[] 48
    $Generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $Generator.GetBytes($Bytes) } finally { $Generator.Dispose() }
    $Value = [Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    Write-SecretFile $Path $Value
    Write-Host "$Label 비밀키: runtime secret 새로 생성"
}

try {
    Write-Host "MemoryPal 통합 설치를 시작합니다." -ForegroundColor Green

    Write-Step "Python 3.12 이상 확인"
    $PythonLauncher = $null
    if (Get-Command python.exe -ErrorAction SilentlyContinue) {
        $PythonCommand = Get-Command python.exe -ErrorAction Stop
        $VersionText = & $PythonCommand.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        Assert-LastExit "Python 버전 확인"
        if ([version]$VersionText -ge [version]"3.12" -and [version]$VersionText -lt [version]"3.13") {
            $PythonLauncher = $PythonCommand.Source
        }
    }
    if (-not $PythonLauncher -and (Get-Command py.exe -ErrorAction SilentlyContinue)) {
        & py.exe -3.12 -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null
        if ($LASTEXITCODE -eq 0) { $PythonLauncher = "py.exe" }
    }
    if (-not $PythonLauncher) {
        throw "Python 3.12.x가 필요합니다. Python 설치 후 다시 실행해 주세요."
    }

    Write-Step "Node.js와 npm 확인"
    $NodeCommand = Get-Command node.exe -ErrorAction Stop
    $NodeMajor = [int]((& $NodeCommand.Source -p "process.versions.node.split('.')[0]").Trim())
    if ($NodeMajor -lt 20) { throw "Node.js 20 이상이 필요합니다." }
    $NpmCommand = (Get-Command npm.cmd -ErrorAction Stop).Source

    Write-Step "공용 Python 가상환경 준비"
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        if ($PythonLauncher -eq "py.exe") {
            & py.exe -3.12 -m venv $Venv
        } else {
            & $PythonLauncher -m venv $Venv
        }
        Assert-LastExit "가상환경 생성"
    }
    & $VenvPython -m pip install --upgrade pip setuptools wheel
    Assert-LastExit "pip 기본 도구 설치"
    & $VenvPython -m pip install -e $Gateway
    Assert-LastExit "Gateway 의존성 설치"

    Write-Step "통합 환경 설정 준비"
    if (-not (Test-Path -LiteralPath $RootEnv)) {
        $Template = Join-Path $Root ".env.example"
        $Content = [IO.File]::ReadAllText($Template)
        [IO.File]::WriteAllText($RootEnv, $Content, $Utf8NoBom)
        Write-Host "루트 .env를 생성했습니다. 비밀값은 별도 runtime 파일에 저장합니다."
    } else {
        Write-Host "기존 루트 .env를 보존합니다."
    }
    $EnvContent = [IO.File]::ReadAllText($RootEnv)
    $ExistingJwtSecret = Get-DotEnvValue $EnvContent "MEMORYPAL_JWT_SECRET"
    $ExistingModelSecret = Get-DotEnvValue $EnvContent "MEMORYPAL_MODEL_SERVICE_TOKEN"
    $ExistingArchiveSecret = Get-DotEnvValue $EnvContent "MEMORYPAL_ARCHIVE_SERVICE_TOKEN"
    Initialize-SecretFile (Join-Path $Secrets "jwt-secret") "JWT" $ExistingJwtSecret
    Initialize-SecretFile `
        (Join-Path $Secrets "model-service-token") `
        "STT/TTS service" `
        $ExistingModelSecret
    Initialize-SecretFile `
        (Join-Path $Secrets "archive-service-token") `
        "Archive service" `
        $ExistingArchiveSecret

    # Durable secrets are written first. Only after that succeeds are legacy
    # inline values removed from .env, preserving existing JWT sessions.
    $EnvContent = [Text.RegularExpressions.Regex]::Replace(
        $EnvContent,
        '(?m)^MEMORYPAL_JWT_SECRET=[^\r\n]*(?=\r?$)',
        'MEMORYPAL_JWT_SECRET='
    )
    $EnvContent = [Text.RegularExpressions.Regex]::Replace(
        $EnvContent,
        '(?m)^MEMORYPAL_MODEL_SERVICE_TOKEN=[^\r\n]*(?=\r?$)',
        'MEMORYPAL_MODEL_SERVICE_TOKEN='
    )
    $EnvContent = [Text.RegularExpressions.Regex]::Replace(
        $EnvContent,
        '(?m)^MEMORYPAL_ARCHIVE_SERVICE_TOKEN=[^\r\n]*(?=\r?$)',
        'MEMORYPAL_ARCHIVE_SERVICE_TOKEN='
    )
    if (
        -not [String]::IsNullOrWhiteSpace($JwtSecretFromCaller) -and
        [String]::IsNullOrWhiteSpace($JwtSecretFileFromCaller)
    ) {
        if ($EnvContent -match '(?m)^MEMORYPAL_JWT_SECRET_FILE=[^\r\n]*(?=\r?$)') {
            $EnvContent = [Text.RegularExpressions.Regex]::Replace(
                $EnvContent,
                '(?m)^MEMORYPAL_JWT_SECRET_FILE=[^\r\n]*(?=\r?$)',
                'MEMORYPAL_JWT_SECRET_FILE='
            )
        } else {
            $EnvContent += "`r`nMEMORYPAL_JWT_SECRET_FILE=`r`n"
        }
    } elseif (Test-UsableSecret $ExistingJwtSecret) {
        if ($EnvContent -match '(?m)^MEMORYPAL_JWT_SECRET_FILE=[^\r\n]*(?=\r?$)') {
            $EnvContent = [Text.RegularExpressions.Regex]::Replace(
                $EnvContent,
                '(?m)^MEMORYPAL_JWT_SECRET_FILE=[^\r\n]*(?=\r?$)',
                'MEMORYPAL_JWT_SECRET_FILE=./.runtime/secrets/jwt-secret'
            )
        } else {
            $EnvContent += "`r`nMEMORYPAL_JWT_SECRET_FILE=./.runtime/secrets/jwt-secret`r`n"
        }
    } elseif ($EnvContent -notmatch '(?m)^MEMORYPAL_JWT_SECRET_FILE=[^\r\n]*(?=\r?$)') {
        $EnvContent += "`r`nMEMORYPAL_JWT_SECRET_FILE=./.runtime/secrets/jwt-secret`r`n"
    } elseif ([String]::IsNullOrWhiteSpace((Get-DotEnvValue $EnvContent "MEMORYPAL_JWT_SECRET_FILE"))) {
        $EnvContent = [Text.RegularExpressions.Regex]::Replace(
            $EnvContent,
            '(?m)^MEMORYPAL_JWT_SECRET_FILE=[^\r\n]*(?=\r?$)',
            'MEMORYPAL_JWT_SECRET_FILE=./.runtime/secrets/jwt-secret'
        )
    }
    if (
        -not [String]::IsNullOrWhiteSpace($ModelSecretFromCaller) -and
        [String]::IsNullOrWhiteSpace($ModelSecretFileFromCaller)
    ) {
        if ($EnvContent -match '(?m)^MEMORYPAL_MODEL_SERVICE_TOKEN_FILE=[^\r\n]*(?=\r?$)') {
            $EnvContent = [Text.RegularExpressions.Regex]::Replace(
                $EnvContent,
                '(?m)^MEMORYPAL_MODEL_SERVICE_TOKEN_FILE=[^\r\n]*(?=\r?$)',
                'MEMORYPAL_MODEL_SERVICE_TOKEN_FILE='
            )
        } else {
            $EnvContent += "`r`nMEMORYPAL_MODEL_SERVICE_TOKEN_FILE=`r`n"
        }
    } elseif (Test-UsableSecret $ExistingModelSecret) {
        if ($EnvContent -match '(?m)^MEMORYPAL_MODEL_SERVICE_TOKEN_FILE=[^\r\n]*(?=\r?$)') {
            $EnvContent = [Text.RegularExpressions.Regex]::Replace(
                $EnvContent,
                '(?m)^MEMORYPAL_MODEL_SERVICE_TOKEN_FILE=[^\r\n]*(?=\r?$)',
                'MEMORYPAL_MODEL_SERVICE_TOKEN_FILE=./.runtime/secrets/model-service-token'
            )
        } else {
            $EnvContent += "`r`nMEMORYPAL_MODEL_SERVICE_TOKEN_FILE=./.runtime/secrets/model-service-token`r`n"
        }
    } elseif ($EnvContent -notmatch '(?m)^MEMORYPAL_MODEL_SERVICE_TOKEN_FILE=[^\r\n]*(?=\r?$)') {
        $EnvContent += "`r`nMEMORYPAL_MODEL_SERVICE_TOKEN_FILE=./.runtime/secrets/model-service-token`r`n"
    } elseif ([String]::IsNullOrWhiteSpace((Get-DotEnvValue $EnvContent "MEMORYPAL_MODEL_SERVICE_TOKEN_FILE"))) {
        $EnvContent = [Text.RegularExpressions.Regex]::Replace(
            $EnvContent,
            '(?m)^MEMORYPAL_MODEL_SERVICE_TOKEN_FILE=[^\r\n]*(?=\r?$)',
            'MEMORYPAL_MODEL_SERVICE_TOKEN_FILE=./.runtime/secrets/model-service-token'
        )
    }
    if (
        -not [String]::IsNullOrWhiteSpace($ArchiveSecretFromCaller) -and
        [String]::IsNullOrWhiteSpace($ArchiveSecretFileFromCaller)
    ) {
        if ($EnvContent -match '(?m)^MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE=[^\r\n]*(?=\r?$)') {
            $EnvContent = [Text.RegularExpressions.Regex]::Replace(
                $EnvContent,
                '(?m)^MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE=[^\r\n]*(?=\r?$)',
                'MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE='
            )
        } else {
            $EnvContent += "`r`nMEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE=`r`n"
        }
    } elseif (Test-UsableSecret $ExistingArchiveSecret) {
        if ($EnvContent -match '(?m)^MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE=[^\r\n]*(?=\r?$)') {
            $EnvContent = [Text.RegularExpressions.Regex]::Replace(
                $EnvContent,
                '(?m)^MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE=[^\r\n]*(?=\r?$)',
                'MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE=./.runtime/secrets/archive-service-token'
            )
        } else {
            $EnvContent += "`r`nMEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE=./.runtime/secrets/archive-service-token`r`n"
        }
    } elseif ($EnvContent -notmatch '(?m)^MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE=[^\r\n]*(?=\r?$)') {
        $EnvContent += "`r`nMEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE=./.runtime/secrets/archive-service-token`r`n"
    } elseif ([String]::IsNullOrWhiteSpace((Get-DotEnvValue $EnvContent "MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE"))) {
        $EnvContent = [Text.RegularExpressions.Regex]::Replace(
            $EnvContent,
            '(?m)^MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE=[^\r\n]*(?=\r?$)',
            'MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE=./.runtime/secrets/archive-service-token'
        )
    }
    [IO.File]::WriteAllText($RootEnv, $EnvContent, $Utf8NoBom)
    Import-DotEnv $RootEnv
    # A caller-injected direct secret wins over the repository's default file
    # setting. If the caller explicitly supplied both sources, keep both so
    # load_settings() rejects the ambiguous deployment.
    if (
        -not [String]::IsNullOrWhiteSpace($JwtSecretFromCaller) -and
        [String]::IsNullOrWhiteSpace($JwtSecretFileFromCaller)
    ) {
        [Environment]::SetEnvironmentVariable("MEMORYPAL_JWT_SECRET_FILE", $null, "Process")
    }
    if (
        -not [String]::IsNullOrWhiteSpace($ModelSecretFromCaller) -and
        [String]::IsNullOrWhiteSpace($ModelSecretFileFromCaller)
    ) {
        [Environment]::SetEnvironmentVariable(
            "MEMORYPAL_MODEL_SERVICE_TOKEN_FILE", $null, "Process"
        )
    }
    if (
        -not [String]::IsNullOrWhiteSpace($ArchiveSecretFromCaller) -and
        [String]::IsNullOrWhiteSpace($ArchiveSecretFileFromCaller)
    ) {
        [Environment]::SetEnvironmentVariable(
            "MEMORYPAL_ARCHIVE_SERVICE_TOKEN_FILE", $null, "Process"
        )
    }

    Write-Step "기존 구조와 동일한 SQLite DB 스키마 구축"
    Push-Location $Gateway
    try {
        $DbInitCode = 'from memorypal_api.config import load_settings; from memorypal_api.database import Database; s=load_settings(); db=Database(s.database_path); db.initialize(); print(s.database_path.resolve())'
        & $VenvPython '-c' $DbInitCode
        Assert-LastExit "Database 초기화"
    } finally {
        Pop-Location
    }

    # Frontend/admin dependency and build subprocesses never need server-only
    # credentials. Remove both direct values and secret-file pointers from the
    # environment before invoking npm tooling.
    $AllowedBuildVariables = @(
        "MEMORYPAL_MAIN_PUBLIC_API_URL",
        "MEMORYPAL_PROJECT3_PUBLIC_API_URL"
    )
    foreach ($EnvironmentName in [Environment]::GetEnvironmentVariables("Process").Keys) {
        $Name = [string]$EnvironmentName
        if (
            $Name.StartsWith("MEMORYPAL_", [StringComparison]::OrdinalIgnoreCase) -and
            $Name -notin $AllowedBuildVariables
        ) {
            [Environment]::SetEnvironmentVariable($Name, $null, "Process")
        }
    }

    Write-Step "Frontend 의존성 설치"
    Push-Location $Frontend
    try {
        if (Test-Path -LiteralPath (Join-Path $Frontend "package-lock.json")) {
            & $NpmCommand ci
        } else {
            & $NpmCommand install
        }
        Assert-LastExit "Frontend 패키지 설치"

        Write-Step "Frontend main/project3 배포 번들 생성"
        & $NpmCommand run build:web
        Assert-LastExit "Frontend main 빌드"
        & $NpmCommand run build:web:project3
        Assert-LastExit "Frontend project3 빌드"
    } finally {
        Pop-Location
    }

    Write-Step "관리자 페이지 의존성 설치"
    Push-Location $Admin
    try {
        if (Test-Path -LiteralPath (Join-Path $Admin "package-lock.json")) {
            & $NpmCommand ci
        } else {
            & $NpmCommand install
        }
        Assert-LastExit "관리자 페이지 패키지 설치"

        Write-Step "관리자 페이지 main/project3 배포 번들 생성"
        & $NpmCommand run build
        Assert-LastExit "관리자 페이지 main 빌드"
        & $NpmCommand run build:project3
        Assert-LastExit "관리자 페이지 project3 빌드"
    } finally {
        Pop-Location
    }

    New-Item -ItemType Directory -Force -Path (Join-Path $Runtime "logs") | Out-Null

    Write-Host "`n설치가 완료되었습니다." -ForegroundColor Green
    Write-Host "실행: run.cmd"
    Write-Host "Gateway DB와 기존 환경 설정은 이후 재설치에서도 보존됩니다."
    exit 0
} catch {
    Write-Host "`n설치 실패: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
