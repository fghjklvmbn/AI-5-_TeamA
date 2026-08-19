[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("default", "companion")]
    [string]$Persona,

    [string]$HostAddress = "192.168.2.41:1234",

    [ValidateRange(1024, 262144)]
    [int]$ContextLength = 40960,

    [ValidateRange(60, 86400)]
    [int]$TtlSeconds = 3600,

    [switch]$KeepOtherModels
)

$ErrorActionPreference = "Stop"

$Lms = Get-Command lms -ErrorAction SilentlyContinue
if (-not $Lms) {
    throw "LM Studio CLI(lms)가 없습니다. LLM 서버에서 'npx lmstudio install-cli'를 먼저 실행해 주세요."
}

$Models = @{
    default = @{
        Key = "qwen/qwen3.5-4b"
        Identifier = "qwen3.5-4b"
    }
    companion = @{
        Key = "memorypal_ai"
        Identifier = "memorypal_ai"
    }
}

$Selected = $Models[$Persona]

# A GTX 1660 SUPER should keep only the selected persona model resident.
# This also prevents JIT-loaded models with automatic/partial offload settings
# from remaining in VRAM when the persona changes.
if (-not $KeepOtherModels) {
    & $Lms.Source unload --all --host $HostAddress
    if ($LASTEXITCODE -ne 0) {
        throw "LM Studio의 기존 모델을 언로드하지 못했습니다."
    }
}

Write-Host "[$Persona] $($Selected.Key) 모델을 GPU full offload로 로드합니다." -ForegroundColor Cyan
& $Lms.Source load $Selected.Key `
    --identifier $Selected.Identifier `
    --gpu max `
    --context-length $ContextLength `
    --ttl $TtlSeconds `
    --host $HostAddress

if ($LASTEXITCODE -ne 0) {
    throw "LM Studio 모델 로드에 실패했습니다."
}

Write-Host "완료: identifier=$($Selected.Identifier), gpu=max, context=$ContextLength, ttl=$TtlSeconds" -ForegroundColor Green
