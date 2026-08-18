# Wave 8.3 production attribution: verify deploy, then 20-turn + barge matrix.
#
# Usage (from SAM repo root, worker/.env + Render API env set):
#   .\scripts\run-wave83-production.ps1
#   .\scripts\run-wave83-production.ps1 -SkipDeploy

param(
    [switch]$SkipDeploy,
    [double]$InterTurnDelay = 20
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Worker = Join-Path $Root "worker"
$Manifest = Join-Path $Worker "bench\audio\manifest.json"
$OutDir = Join-Path $Worker "bench\evidence\wave83"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

if (-not $SkipDeploy) {
    & (Join-Path $PSScriptRoot "deploy-sam-agent.ps1")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& (Join-Path $PSScriptRoot "verify-sam-agent.ps1") `
    -Wait `
    -ExpectedEnv @(
        "SAM_TURN_MODE=stt",
        "SAM_BRAIN=groq",
        "SAM_INTERRUPTION_MODE=vad",
        "SAM_STT_MODEL=deepgram/nova-3",
        "GROQ_MODEL=openai/gpt-oss-20b",
        "SAM_LLM_MAX_COMPLETION_TOKENS=256"
    ) `
    -RequiredEnv @("DEEPGRAM_API_KEY", "GROQ_API_KEY")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$competingWorkers = @(
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -match 'python(?:\.exe)?[" ]+.*-m\s+sam_worker\.agent\s+(?:start|dev)'
    }
)
if ($competingWorkers.Count -gt 0) {
    $ids = ($competingWorkers | ForEach-Object { $_.ProcessId }) -join ", "
    throw "Competing unnamed local SAM worker(s) detected (PID $ids). Stop them before production attribution."
}

$output = Join-Path $OutDir "production-20turn.json"
Write-Host "=== wave83 production 20-turn ===" -ForegroundColor Cyan
Push-Location $Worker
try {
    python -m sam_worker.bench.run_audio_bench `
        $Manifest `
        --output $output `
        --turn-mode stt `
        --interruption-mode vad `
        --agent-timeout 180 `
        --turn-timeout 45 `
        --inter-turn-delay $InterTurnDelay `
        --expect-worker-info turn_mode=stt `
        --expect-worker-info resolved_brain=groq `
        --expect-worker-info brain=groq:openai/gpt-oss-20b `
        --expect-worker-info interruption_mode=vad `
        --expect-worker-info llm_max_completion_tokens=256 `
        --expect-worker-info stt_model=deepgram/nova-3 `
        --expect-worker-info surface=portal `
        --arm wave83-production
    if ($LASTEXITCODE -ne 0) {
        throw "production matrix failed with exit $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Host "Wave 8.3 production evidence: $output" -ForegroundColor Green
