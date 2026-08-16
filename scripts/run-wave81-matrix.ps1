# Wave 8.1 experiment matrix: endpointing variants + brain bake-off.
#
# Usage (from SAM repo root, worker/.env loaded by the bench):
#   .\scripts\run-wave81-matrix.ps1
#   .\scripts\run-wave81-matrix.ps1 -SkipBrain
#   .\scripts\run-wave81-matrix.ps1 -MaxTurns 6

param(
    [int]$MaxTurns = 10,
    [switch]$SkipEndpoint,
    [switch]$SkipBrain,
    [switch]$SkipBarge
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Worker = Join-Path $Root "worker"
$Manifest = Join-Path $Worker "bench\audio\manifest.json"
$OutDir = Join-Path $Worker "bench\evidence\wave81"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Invoke-AudioBench {
    param(
        [string]$Name,
        [string[]]$ExtraArgs
    )
    $output = Join-Path $OutDir "$Name.json"
    Write-Host "=== $Name ===" -ForegroundColor Cyan
    $args = @(
        "-m", "sam_worker.bench.run_audio_bench",
        $Manifest,
        "--output", $output,
        "--embedded-agent",
        "--max-turns", "$MaxTurns"
    ) + $ExtraArgs
    if ($SkipBarge) { $args += "--skip-barge" }
    Push-Location $Worker
    try {
        python @args
        if ($LASTEXITCODE -notin 0, 2) {
            throw "bench $Name failed with exit $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

if (-not $SkipEndpoint) {
    Invoke-AudioBench "eou-stt-0.3-1.2" @(
        "--turn-mode", "stt", "--endpoint-min", "0.3", "--endpoint-max", "1.2", "--arm", "eou-stt-control"
    )
    Invoke-AudioBench "eou-stt-0.25-0.6" @(
        "--turn-mode", "stt", "--endpoint-min", "0.25", "--endpoint-max", "0.6", "--arm", "eou-stt-tight"
    )
    Invoke-AudioBench "eou-vad-0.25-0.6" @(
        "--turn-mode", "vad", "--endpoint-min", "0.25", "--endpoint-max", "0.6", "--arm", "eou-vad"
    )
    Invoke-AudioBench "eou-mini-0.3-0.8" @(
        "--turn-mode", "mini", "--endpoint-min", "0.3", "--endpoint-max", "0.8", "--arm", "eou-mini"
    )
}

if (-not $SkipBrain) {
    Invoke-AudioBench "brain-openai-4o-mini" @(
        "--turn-mode", "stt", "--sam-brain", "openai", "--llm-model", "gpt-4o-mini", "--arm", "openai-4o-mini"
    )
    Invoke-AudioBench "brain-groq-8b" @(
        "--turn-mode", "stt", "--sam-brain", "groq", "--llm-model", "llama-3.1-8b-instant", "--arm", "groq-8b"
    )
    Invoke-AudioBench "brain-groq-70b" @(
        "--turn-mode", "stt", "--sam-brain", "groq", "--llm-model", "llama-3.3-70b-versatile", "--arm", "groq-70b"
    )
}

Write-Host "Wave 8.1 matrix written to $OutDir" -ForegroundColor Green
