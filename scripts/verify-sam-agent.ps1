# Poll sam-agent deploy status and print live env via the Render API.
#
# Usage (from SAM repo root):
#   .\scripts\verify-sam-agent.ps1
#   .\scripts\verify-sam-agent.ps1 -Wait
#   .\scripts\verify-sam-agent.ps1 -Wait -ExpectedCommit (git rev-parse HEAD)
#
# Requires RENDER_API_KEY and either SAM_AGENT_SERVICE_ID or SAM_AGENT_DEPLOY_HOOK_URL.

param(
    [switch]$Wait,
    [int]$TimeoutSec = 900,
    [string]$ExpectedCommit = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_render_sam_agent.ps1")
$creds = Assert-SamAgentRenderCredentials
$serviceId = $creds.ServiceId
$headers = $creds.Headers

function Get-LatestDeploy {
    Get-SamAgentLatestDeploy -ServiceId $serviceId -Headers $headers
}

function Get-EnvMap {
    $rows = Invoke-RenderGet -Uri "https://api.render.com/v1/services/$serviceId/env-vars?limit=100" -Headers $headers
    $map = @{}
    foreach ($row in $rows) {
        $env = $row.envVar
        if (-not $env) { $env = $row }
        $key = [string]$env.key
        if ($key) { $map[$key] = [string]$env.value }
    }
    return $map
}

$deadline = (Get-Date).AddSeconds($TimeoutSec)
$attempt = 0
do {
    $attempt++
    $deploy = Get-LatestDeploy
    $status = [string]$deploy.status
    $deployId = [string]$deploy.id
    $commit = ""
    if ($deploy.commit -and $deploy.commit.id) {
        $commit = [string]$deploy.commit.id
    }
    Write-Host "deploy=$deployId status=$status commit=$commit" -ForegroundColor Cyan
    if ($status -in @("live")) {
        break
    }
    if ($status -in @("build_failed", "update_failed", "canceled", "deactivated")) {
        Write-Host ""
        Write-Host "Build log: https://dashboard.render.com/web/$serviceId/deploys/$deployId" -ForegroundColor Red
        throw "sam-agent deploy $deployId ended in status=$status"
    }
    if (-not $Wait) {
        Write-Host "Deploy not live yet (status=$status). Re-run with -Wait." -ForegroundColor Yellow
        exit 2
    }
    if ((Get-Date) -ge $deadline) {
        throw "Timed out waiting for sam-agent deploy to reach live (last status=$status)"
    }
    Start-Sleep -Seconds 15
} while ($true)

$envMap = Get-EnvMap
$watch = @("SAM_BRAIN", "SAM_ENDPOINTING_MIN", "SAM_ENDPOINTING_MAX", "SAM_HISTORY_TOKEN_CAP", "GROQ_MODEL", "SAM_TURN_MODE")
Write-Host "sam-agent env:" -ForegroundColor Green
foreach ($name in $watch) {
    if ($envMap.ContainsKey($name)) {
        Write-Host "  $name=$($envMap[$name])"
    } else {
        Write-Host "  $name=(unset)"
    }
}

if (-not $ExpectedCommit) {
    Push-Location (Split-Path $PSScriptRoot -Parent)
    try {
        $ExpectedCommit = (git rev-parse HEAD).Trim()
    } finally {
        Pop-Location
    }
}
$ExpectedCommit = $ExpectedCommit.Trim()
if ($ExpectedCommit -and $commit) {
    if ($commit.StartsWith($ExpectedCommit) -or $ExpectedCommit.StartsWith($commit)) {
        Write-Host "commit match: live=$commit expected=$ExpectedCommit" -ForegroundColor Green
    } else {
        throw "commit mismatch: live=$commit expected=$ExpectedCommit"
    }
}

Write-Host "sam-agent is live on $serviceId" -ForegroundColor Green
