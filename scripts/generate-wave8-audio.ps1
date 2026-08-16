[CmdletBinding()]
param(
    [string]$Manifest = (Join-Path $PSScriptRoot "..\worker\bench\audio\manifest.json")
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

$manifestPath = (Resolve-Path $Manifest).Path
$root = Split-Path $manifestPath -Parent
$payload = Get-Content $manifestPath -Raw | ConvertFrom-Json
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
    16000,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono
)

foreach ($fixture in $payload.fixtures) {
    $destination = Join-Path $root ([string]$fixture.file)
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    try {
        $synth.Rate = 0
        $synth.SetOutputToWaveFile($destination, $format)
        $synth.Speak([string]$fixture.transcript)
    }
    finally {
        $synth.Dispose()
    }
}

Write-Host "Generated $($payload.fixtures.Count) synthetic PCM fixtures in $root"
