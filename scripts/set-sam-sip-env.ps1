# Bootstrap the SAM_SIP_* values in worker/.env for the owner-only inbound pilot.
# Reuses existing credentials when present so reruns stay idempotent.

param(
    [string]$PilotNumber = "+18556343880",
    [string]$OwnerNumbers = "",
    [string]$LiveKitSipHost = "",
    [string]$RainmakerServiceId = "srv-d8e1sk4m0tmc73eeq42g"
)

$ErrorActionPreference = "Stop"

$EnvPath = Join-Path $PSScriptRoot "..\worker\.env"
if (-not (Test-Path $EnvPath)) { throw "worker/.env not found at $EnvPath" }

function Get-EnvValue([string]$Key) {
    $line = Get-Content $EnvPath | Where-Object { $_ -match "^\s*$([regex]::Escape($Key))=" } | Select-Object -First 1
    if (-not $line) { return "" }
    return ($line -replace "^\s*$([regex]::Escape($Key))=", "").Trim()
}

function Set-EnvValue([string]$Key, [string]$Value) {
    $lines = @(Get-Content $EnvPath)
    $pattern = "^\s*$([regex]::Escape($Key))="
    if ($lines -match $pattern) {
        $lines = $lines | ForEach-Object { if ($_ -match $pattern) { "$Key=$Value" } else { $_ } }
    } else {
        $lines += "$Key=$Value"
    }
    Set-Content -Path $EnvPath -Value $lines -Encoding UTF8
}

# Owner allow-list: default to the same number the rm_api owner gate trusts.
if (-not $OwnerNumbers) {
    $OwnerNumbers = Get-EnvValue "SAM_SIP_OWNER_NUMBERS"
}
if (-not $OwnerNumbers) {
    $key = [Environment]::GetEnvironmentVariable("RENDER_API_KEY", "User")
    if (-not $key) { throw "RENDER_API_KEY not set and -OwnerNumbers not supplied" }
    $headers = @{ Authorization = "Bearer $key"; Accept = "application/json" }
    $uri = "https://api.render.com/v1/services/$RainmakerServiceId/env-vars?limit=100"
    $rows = Invoke-RestMethod -Uri $uri -Headers $headers -TimeoutSec 30
    foreach ($row in $rows) {
        $item = if ($row.envVar) { $row.envVar } else { $row }
        if ([string]$item.key -eq "RM_ALERT_TO") { $OwnerNumbers = ([string]$item.value).Trim() }
    }
}
if (-not $OwnerNumbers) { throw "Could not resolve owner number (RM_ALERT_TO)" }

$username = Get-EnvValue "SAM_SIP_AUTH_USERNAME"
if (-not $username) { $username = "sam-inbound" }

# Alphanumeric only: the password is interpolated into SIP URIs and TwiML attributes.
$password = Get-EnvValue "SAM_SIP_AUTH_PASSWORD"
if (-not $password) {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $password = ([Convert]::ToBase64String($bytes) -replace '[^A-Za-z0-9]', '').Substring(0, 28)
}

if (-not $LiveKitSipHost) { $LiveKitSipHost = Get-EnvValue "SAM_SIP_LIVEKIT_HOST" }

Set-EnvValue "SAM_SIP_PILOT_NUMBER" $PilotNumber
Set-EnvValue "SAM_SIP_OWNER_NUMBERS" $OwnerNumbers
Set-EnvValue "SAM_SIP_AUTH_USERNAME" $username
Set-EnvValue "SAM_SIP_AUTH_PASSWORD" $password
Set-EnvValue "SAM_SIP_LIVEKIT_HOST" $LiveKitSipHost

Write-Host "worker/.env updated:" -ForegroundColor Green
Write-Host "  SAM_SIP_PILOT_NUMBER   = $PilotNumber"
Write-Host "  SAM_SIP_OWNER_NUMBERS  = set (...$($OwnerNumbers.Substring([Math]::Max(0, $OwnerNumbers.Length - 4))))"
Write-Host "  SAM_SIP_AUTH_USERNAME  = $username"
Write-Host "  SAM_SIP_AUTH_PASSWORD  = set ($($password.Length) chars, not shown)"
if ($LiveKitSipHost) {
    Write-Host "  SAM_SIP_LIVEKIT_HOST   = $LiveKitSipHost"
} else {
    Write-Host "  SAM_SIP_LIVEKIT_HOST   = MISSING" -ForegroundColor Yellow
    Write-Host "    Copy the SIP URI host from cloud.livekit.io -> Project settings," -ForegroundColor Yellow
    Write-Host "    then rerun with -LiveKitSipHost <subdomain>.sip.livekit.cloud" -ForegroundColor Yellow
}
