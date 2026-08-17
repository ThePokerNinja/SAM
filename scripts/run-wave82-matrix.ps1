# Wave 8.2 brain bake-off on the shrunk prompt.
#
# Usage (from SAM repo root):
#   .\scripts\run-wave82-matrix.ps1
#   .\scripts\run-wave82-matrix.ps1 -MaxTurns 8
#   .\scripts\run-wave82-matrix.ps1 -SkipBarge

param(
    [int]$MaxTurns = 8,
    [switch]$SkipBarge
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Worker = Join-Path $Root "worker"
$Manifest = Join-Path $Worker "bench\audio\manifest.json"
$OutDir = Join-Path $Worker "bench\evidence\wave82"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Invoke-AudioBench {
    param(
        [string]$Name,
        [string[]]$ExtraArgs
    )
    $output = Join-Path $OutDir "$Name.json"
    Write-Host "=== $Name ===" -ForegroundColor Cyan
    $benchArgs = @(
        "-m", "sam_worker.bench.run_audio_bench",
        $Manifest,
        "--output", $output,
        "--embedded-agent",
        "--max-turns", "$MaxTurns",
        "--turn-mode", "stt",
        "--endpoint-min", "0.25",
        "--endpoint-max", "0.6"
    ) + $ExtraArgs
    if ($SkipBarge) { $benchArgs += "--skip-barge" }
    Push-Location $Worker
    try {
        python @benchArgs
        if ($LASTEXITCODE -notin 0, 2) {
            throw "bench $Name failed with exit $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

Invoke-AudioBench "brain-openai-4o-mini" @(
    "--sam-brain", "openai", "--llm-model", "gpt-4o-mini", "--arm", "openai-4o-mini"
)
Invoke-AudioBench "brain-groq-8b" @(
    "--sam-brain", "groq", "--llm-model", "llama-3.1-8b-instant", "--arm", "groq-8b"
)
Invoke-AudioBench "brain-groq-70b" @(
    "--sam-brain", "groq", "--llm-model", "llama-3.3-70b-versatile", "--arm", "groq-70b"
)

Write-Host "Wave 8.2 matrix written to $OutDir" -ForegroundColor Green
