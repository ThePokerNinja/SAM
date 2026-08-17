# Fire the sam-agent deploy hook. Optionally wait until Render reports live.
# Does not print the hook URL.
#
# Usage (from SAM repo root):
#   .\scripts\deploy-sam-agent.ps1
#   .\scripts\deploy-sam-agent.ps1 -Wait

param(
    [switch]$Wait,
    [int]$WaitTimeoutSec = 900
)

$ErrorActionPreference = "Stop"
$hook = ($(if ($env:SAM_AGENT_DEPLOY_HOOK_URL) {
    $env:SAM_AGENT_DEPLOY_HOOK_URL
} elseif ($env:RENDER_DEPLOY_HOOK_URL) {
    $env:RENDER_DEPLOY_HOOK_URL
} else {
    ""
})).Trim()
if (-not $hook) { throw "SAM_AGENT_DEPLOY_HOOK_URL or RENDER_DEPLOY_HOOK_URL is not set" }
try {
    $res = Invoke-WebRequest -Method POST -Uri $hook -UseBasicParsing -TimeoutSec 90
    Write-Host "sam-agent deploy hook $($res.StatusCode)"
} catch {
    $resp = $_.Exception.Response
    if (-not $resp) { throw "No HTTP response - request never reached Render: $($_.Exception.Message)" }
    throw "sam-agent deploy hook HTTP $([int]$resp.StatusCode)"
}

if ($Wait) {
    & (Join-Path $PSScriptRoot "verify-sam-agent.ps1") -Wait -TimeoutSec $WaitTimeoutSec
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
