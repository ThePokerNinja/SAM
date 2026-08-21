# SAM-043/044 lab proof: write a session artifact, then recall it in a new room.
# Production LiveKit audio. No phone call. Costs Groq + ElevenLabs.
#
# Usage (SAM repo):
#   .\scripts\run-artifact-proof.ps1
# Close looks like: recall evidence contains prior_artifact_brief with count > 0.
# Default 35s settle: LiveKit runs one process per job; session-close persist can
# lag ~20s after the bench disconnects. 8s was not enough on the first lab run.

param(
    [string]$WriteManifest = "worker\bench\audio\agent-os-artifact-write-manifest.json",
    [string]$RecallManifest = "worker\bench\audio\agent-os-artifact-recall-manifest.json",
    [int]$SettleSeconds = 35
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

foreach ($path in @($WriteManifest, $RecallManifest)) {
    if (-not (Test-Path $path)) { throw "manifest missing: $path" }
}

$sha = (git rev-parse --short HEAD).Trim()
$outDir = Join-Path (Get-Location) "worker\bench\evidence"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$writeOut = Join-Path $outDir "agent-os-artifact-write-live-$sha.json"
$recallOut = Join-Path $outDir "agent-os-artifact-recall-live-$sha.json"
$writeManifestPath = (Resolve-Path $WriteManifest).Path
$recallManifestPath = (Resolve-Path $RecallManifest).Path

function Invoke-ArtifactArm {
    param(
        [string]$Name,
        [string]$Manifest,
        [string]$Output
    )
    Write-Host "=== $Name ===" -ForegroundColor Cyan
    Push-Location worker
    try {
        python -m sam_worker.bench.run_audio_bench `
            $Manifest `
            --output $Output `
            --turn-mode stt `
            --skip-barge `
            --owner-test-token `
            --agent-timeout 180 `
            --turn-timeout 45 `
            --expect-worker-info turn_mode=stt `
            --expect-worker-info resolved_brain=groq
        if ($LASTEXITCODE -ne 0) {
            throw "$Name audio bench failed with exit $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

Invoke-ArtifactArm "artifact-write" $writeManifestPath $writeOut
Write-Host "waiting ${SettleSeconds}s for session-close artifact persist" -ForegroundColor Yellow
Start-Sleep -Seconds $SettleSeconds
Invoke-ArtifactArm "artifact-recall" $recallManifestPath $recallOut

$write = Get-Content $writeOut -Raw | ConvertFrom-Json
$recall = Get-Content $recallOut -Raw | ConvertFrom-Json
$writeTypes = @($write.results | ForEach-Object { $_.agent_event_types }) | ForEach-Object { $_ }
$recallTypes = @($recall.results | ForEach-Object { $_.agent_event_types }) | ForEach-Object { $_ }

Write-Host "write events: $($writeTypes -join ', ')"
Write-Host "recall events: $($recallTypes -join ', ')"
Write-Host "recall assistant: $($recall.results[0].assistant_text)"

if ($writeTypes -notcontains "artifact_checkpoint") {
    Write-Host "write run did not publish artifact_checkpoint (memory may still be off)" -ForegroundColor Yellow
}
if ($recallTypes -notcontains "prior_artifact_brief") {
    throw "SAM-043/044 not closed: recall missing prior_artifact_brief (events: $($recallTypes -join ', '))"
}

Write-Host "SAM-043/044 lab proof passed: prior_artifact_brief present" -ForegroundColor Green
Write-Host "write:   $writeOut"
Write-Host "recall:  $recallOut"
