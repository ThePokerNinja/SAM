# Update one non-secret sam-agent env var via the Render API.
# Deploy hooks do not overwrite dashboard values (Wave 8.1 lesson).
#
# Usage (from SAM repo root):
#   .\scripts\set-sam-agent-env.ps1 -Key SAM_BRAIN -Value groq
#
# Requires RENDER_API_KEY + SAM_AGENT_SERVICE_ID.
# Updates a single key only — never replaces the full env set.

param(
    [Parameter(Mandatory = $true)][string]$Key,
    [Parameter(Mandatory = $true)][string]$Value
)

$ErrorActionPreference = "Stop"
$apiKey = ($(if ($env:RENDER_API_KEY) { $env:RENDER_API_KEY } else { "" })).Trim()
$serviceId = ($(if ($env:SAM_AGENT_SERVICE_ID) { $env:SAM_AGENT_SERVICE_ID } else { "" })).Trim()
if (-not $apiKey -or -not $serviceId) {
    throw "RENDER_API_KEY and SAM_AGENT_SERVICE_ID are required"
}

$headers = @{
    Authorization  = "Bearer $apiKey"
    Accept         = "application/json"
    "Content-Type" = "application/json"
}
$uri = "https://api.render.com/v1/services/$serviceId/env-vars/$Key"
$body = @{ value = $Value } | ConvertTo-Json
$res = Invoke-RestMethod -Method PUT -Uri $uri -Headers $headers -Body $body -TimeoutSec 30
$env = $res.envVar
if (-not $env) { $env = $res }
Write-Host "Updated $Key on $serviceId to $($env.value)"
