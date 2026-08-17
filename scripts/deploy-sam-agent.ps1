# Push is assumed already done. Fire the sam-agent deploy hook only.
# Does not print the hook URL.

$ErrorActionPreference = "Stop"
$hook = ($(if ($env:SAM_AGENT_DEPLOY_HOOK_URL) { $env:SAM_AGENT_DEPLOY_HOOK_URL } else { "" })).Trim()
if (-not $hook) { throw "SAM_AGENT_DEPLOY_HOOK_URL is not set" }
try {
    $res = Invoke-WebRequest -Method POST -Uri $hook -UseBasicParsing -TimeoutSec 90
    Write-Host "sam-agent deploy hook $($res.StatusCode)"
} catch {
    $resp = $_.Exception.Response
    if (-not $resp) { throw "No HTTP response - request never reached Render: $($_.Exception.Message)" }
    throw "sam-agent deploy hook HTTP $([int]$resp.StatusCode)"
}
