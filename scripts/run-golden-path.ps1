# Golden-path production audio subset. Opt-in: costs Groq + ElevenLabs.
#
# Usage (SAM repo):
#   .\scripts\run-golden-path.ps1
# Called from rainMaker ship-gate.ps1 when -LiveGoldenPath is set.

param(
    [string]$Manifest = "worker\sam_worker\bench\audio\agent-os-manifest.json"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path $Manifest)) {
    throw "golden-path manifest missing: $Manifest"
}
Write-Host "golden-path: $Manifest" -ForegroundColor Cyan
Push-Location worker
try {
    python -m sam_worker.bench.run_audio_bench --manifest $Manifest --expect-worker-info --owner-test-token
    if ($LASTEXITCODE -ne 0) { throw "golden-path audio bench failed" }
} finally {
    Pop-Location
}
