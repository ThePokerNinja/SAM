# Update one non-secret sam-agent env var via the Render API.
# Deploy hooks do not overwrite dashboard values (Wave 8.1 lesson).
#
# Usage (from SAM repo root):
#   .\scripts\set-sam-agent-env.ps1 -Key SAM_BRAIN -Value groq
#
# Requires RENDER_API_KEY and either SAM_AGENT_SERVICE_ID or SAM_AGENT_DEPLOY_HOOK_URL.
# Updates a single key only — never replaces the full env set.

param(
    [Parameter(Mandatory = $true)][string]$Key,
    [Parameter(Mandatory = $true)][string]$Value
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_render_sam_agent.ps1")
$creds = Assert-SamAgentRenderCredentials
$serviceId = $creds.ServiceId
$headers = $creds.Headers
$uri = "https://api.render.com/v1/services/$serviceId/env-vars/$Key"
$body = @{ value = $Value } | ConvertTo-Json
$res = Invoke-RestMethod -Method PUT -Uri $uri -Headers $headers -Body $body -TimeoutSec 30
$env = $res.envVar
if (-not $env) { $env = $res }
Write-Host "Updated $Key on $serviceId to $($env.value)"
