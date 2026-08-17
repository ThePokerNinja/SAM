# Wave 8.4 turn-detection matrix on the shrunk-prompt Groq build.

param(
    [int]$MaxTurns = 5,
    [double]$InterTurnDelay = 20,
    [switch]$SkipBarge,
    [switch]$PhoneOnly
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Worker = Join-Path $Root "worker"
$Manifest = Join-Path $Worker "bench\audio\manifest.json"
$OutDir = Join-Path $Worker "bench\evidence\wave84"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function New-NarrowbandFixtures {
    $ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if (-not $ffmpeg) {
        throw "ffmpeg is required to generate the 8kHz narrowband benchmark arm"
    }
    $sourceDir = Split-Path $Manifest -Parent
    $targetDir = Join-Path $OutDir "audio-8khz"
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    Copy-Item $Manifest (Join-Path $targetDir "manifest.json") -Force
    foreach ($source in Get-ChildItem $sourceDir -Filter "*.wav") {
        $target = Join-Path $targetDir $source.Name
        & $ffmpeg.Source -y -loglevel error -i $source.FullName -ar 8000 -ac 1 -c:a pcm_s16le $target
        if ($LASTEXITCODE -ne 0) {
            throw "ffmpeg failed to create $target"
        }
    }
    return Join-Path $targetDir "manifest.json"
}

function Invoke-TurnArm {
    param(
        [string]$Name,
        [string]$TurnMode,
        [string]$SttModel = "",
        [string]$ManifestPath = $Manifest,
        [int]$SampleRate = 16000
    )
    $output = Join-Path $OutDir "$Name.json"
    $args = @(
        "-m", "sam_worker.bench.run_audio_bench",
        $ManifestPath,
        "--output", $output,
        "--embedded-agent",
        "--max-turns", "$MaxTurns",
        "--inter-turn-delay", "$InterTurnDelay",
        "--sample-rate", "$SampleRate",
        "--turn-mode", $TurnMode,
        "--sam-brain", "groq",
        "--llm-model", "openai/gpt-oss-20b",
        "--arm", $Name
    )
    if ($SttModel) { $args += @("--stt-model", $SttModel) }
    if ($SkipBarge) { $args += "--skip-barge" }
    Write-Host "=== $Name ===" -ForegroundColor Cyan
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

if (-not $PhoneOnly) {
    Invoke-TurnArm "cloud-groq" "cloud"
    Invoke-TurnArm "mini-groq" "mini"
    Invoke-TurnArm "vad-groq" "vad"
    Invoke-TurnArm "stt-nova3-groq" "stt" "deepgram/nova-3"
    Invoke-TurnArm "stt-flux-500ms-groq" "stt" "deepgram/flux-general-en"
}

$phoneManifest = New-NarrowbandFixtures
Invoke-TurnArm "stt-phonecall-8khz-groq" "stt" "deepgram/nova-2-phonecall" $phoneManifest 8000

python (Join-Path $PSScriptRoot "summarize-wave84-matrix.py") $OutDir
if ($LASTEXITCODE -ne 0) {
    throw "Wave 8.4 matrix summarization failed with exit $LASTEXITCODE"
}
Write-Host "Wave 8.4 matrix written to $OutDir" -ForegroundColor Green
exit 0
