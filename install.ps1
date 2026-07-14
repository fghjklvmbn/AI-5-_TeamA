[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = [IO.Path]::GetFullPath($PSScriptRoot)
$Venv = Join-Path $Root ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$Gateway = Join-Path $Root "backend\gateway"
$Frontend = Join-Path $Root "frontend"
$RootEnv = Join-Path $Root ".env"
$Utf8NoBom = [Text.UTF8Encoding]::new($false)

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
        [Environment]::SetEnvironmentVariable($Pair[0].Trim(), $Pair[1].Trim(), "Process")
    }
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
        $RandomBytes = New-Object byte[] 32
        [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($RandomBytes)
        $Secret = ($RandomBytes | ForEach-Object { $_.ToString("x2") }) -join ""
        $Content = [Text.RegularExpressions.Regex]::Replace(
            $Content,
            '(?m)^MEMORYPAL_JWT_SECRET=.*$',
            "MEMORYPAL_JWT_SECRET=$Secret"
        )
        [IO.File]::WriteAllText($RootEnv, $Content, $Utf8NoBom)
        Write-Host "루트 .env를 생성하고 JWT 비밀키를 무작위로 설정했습니다."
    } else {
        Write-Host "기존 루트 .env를 보존합니다."
    }
    Import-DotEnv $RootEnv

    Write-Step "기존 구조와 동일한 SQLite DB 스키마 구축"
    Push-Location $Gateway
    try {
        $DbInitCode = 'from memorypal_api.config import load_settings; from memorypal_api.database import Database; s=load_settings(); db=Database(s.database_path); db.initialize(); print(s.database_path.resolve())'
        & $VenvPython '-c' $DbInitCode
        Assert-LastExit "Database 초기화"
    } finally {
        Pop-Location
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

        Write-Step "Frontend 배포 번들 생성"
        & $NpmCommand run build:web
        Assert-LastExit "Frontend 빌드"
    } finally {
        Pop-Location
    }

    New-Item -ItemType Directory -Force -Path (Join-Path $Root ".runtime\logs") | Out-Null

    Write-Host "`n설치가 완료되었습니다." -ForegroundColor Green
    Write-Host "실행: run.cmd"
    Write-Host "Gateway DB와 기존 환경 설정은 이후 재설치에서도 보존됩니다."
    exit 0
} catch {
    Write-Host "`n설치 실패: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
