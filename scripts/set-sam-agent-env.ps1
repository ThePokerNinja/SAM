# Update one sam-agent env var via the Render API without printing secrets.
# Deploy hooks do not overwrite dashboard values (Wave 8.1 lesson).
#
# Usage (from SAM repo root):
#   .\scripts\set-sam-agent-env.ps1 -Key SAM_BRAIN -Value groq
#   .\scripts\set-sam-agent-env.ps1 -Key DEEPGRAM_API_KEY -ValueFromDotEnv worker/.env
#
# Requires RENDER_API_KEY and either SAM_AGENT_SERVICE_ID or SAM_AGENT_DEPLOY_HOOK_URL.
# Updates a single key only — never replaces the full env set.

param(
    [Parameter(Mandatory = $true)][string]$Key,
    [string]$Value = "",
    [string]$ValueFromDotEnv = ""
)

$ErrorActionPreference = "Stop"
if ($ValueFromDotEnv) {
    $envPath = Resolve-Path $ValueFromDotEnv
    $match = Get-Content $envPath | Where-Object {
        $_ -match "^\s*$([regex]::Escape($Key))\s*="
    } | Select-Object -First 1
    if (-not $match) { throw "$Key was not found in $envPath" }
    $Value = ($match -split "=", 2)[1].Trim().Trim('"').Trim("'")
}
if ([string]::IsNullOrWhiteSpace($Value)) {
    throw "Provide -Value or -ValueFromDotEnv"
}
. (Join-Path $PSScriptRoot "_render_sam_agent.ps1")
$creds = Assert-SamAgentRenderCredentials
$serviceId = $creds.ServiceId
$headers = $creds.Headers
$uri = "https://api.render.com/v1/services/$serviceId/env-vars/$Key"
$body = @{ value = $Value } | ConvertTo-Json
$res = Invoke-RestMethod -Method PUT -Uri $uri -Headers $headers -Body $body -TimeoutSec 30
$env = $res.envVar
if (-not $env) { $env = $res }
$display = if ($Key -match "(KEY|SECRET|TOKEN|PASSWORD)") { "(set)" } else { [string]$env.value }
Write-Host "Updated $Key on $serviceId to $display"
