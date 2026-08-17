# Wave 8.3 production attribution: verify deploy, then 20-turn + barge matrix.
#
# Usage (from SAM repo root, worker/.env + Render API env set):
#   .\scripts\run-wave83-production.ps1
#   .\scripts\run-wave83-production.ps1 -SkipDeploy

param(
    [switch]$SkipDeploy
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Worker = Join-Path $Root "worker"
$Manifest = Join-Path $Worker "bench\audio\manifest.json"
$OutDir = Join-Path $Worker "bench\evidence\wave83"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

if (-not $SkipDeploy) {
    & (Join-Path $PSScriptRoot "deploy-sam-agent.ps1") -Wait
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    & (Join-Path $PSScriptRoot "verify-sam-agent.ps1") -Wait
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$output = Join-Path $OutDir "production-20turn.json"
Write-Host "=== wave83 production 20-turn ===" -ForegroundColor Cyan
Push-Location $Worker
try {
    python -m sam_worker.bench.run_audio_bench `
        $Manifest `
        --output $output `
        --turn-mode stt `
        --agent-timeout 180 `
        --turn-timeout 45 `
        --arm wave83-production
    if ($LASTEXITCODE -notin 0, 2) {
        throw "production matrix failed with exit $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Host "Wave 8.3 production evidence: $output" -ForegroundColor Green
