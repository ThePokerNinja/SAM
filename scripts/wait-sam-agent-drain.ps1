# Wait until the previous sam-agent instance has drained, so the next phone call runs new code.
#
# Render marks a deploy "live" when the new instance starts, but LiveKit keeps dispatching
# calls to the old worker until it logs "draining worker" (2026-10-17: a call 55s after
# "live" ran the old code). Run after verify-sam-agent.ps1 -Wait, before any live call.
#
# Usage: C:\Users\User\Desktop\SAM\scripts\wait-sam-agent-drain.ps1 [-TimeoutSec 300]

param(
    [int]$TimeoutSec = 300,
    [string]$OwnerId = "tea-d8e1fb4p3tds7383aaf0"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_render_sam_agent.ps1")
$creds = Assert-SamAgentRenderCredentials
$serviceId = $creds.ServiceId
$headers = $creds.Headers

$deploy = Get-SamAgentLatestDeploy -ServiceId $serviceId -Headers $creds.Headers
$since = [DateTime]::Parse($deploy.createdAt).ToUniversalTime().ToString("o")
Write-Host "deploy=$($deploy.id) status=$($deploy.status) since=$since"

$deadline = (Get-Date).AddSeconds($TimeoutSec)
while ((Get-Date) -lt $deadline) {
    $now = (Get-Date).ToUniversalTime().ToString("o")
    $uri = "https://api.render.com/v1/logs?ownerId=$OwnerId&resource=$serviceId&startTime=$since&endTime=$now&limit=100&direction=forward&text=worker"
    $logs = (Invoke-RestMethod -Uri $uri -Headers $headers -TimeoutSec 45).logs
    $instanceOf = { param($row) ($row.labels | Where-Object name -eq "instance").value }
    $started = $logs | Where-Object { $_.message -like '*"starting worker"*' } | Select-Object -Last 1
    if ($started) {
        $newInstance = & $instanceOf $started
        $drained = $logs | Where-Object { $_.message -like '*"draining worker"*' -and (& $instanceOf $_) -ne $newInstance }
        if ($drained) {
            Write-Host "old instance $(& $instanceOf ($drained | Select-Object -First 1)) drained; new instance $newInstance takes calls"
            exit 0
        }
        Write-Host "new instance $newInstance up; old instance still taking calls..."
    } else {
        Write-Host "new instance not started yet..."
    }
    Start-Sleep -Seconds 10
}
throw "Old sam-agent instance did not drain within $TimeoutSec s. Do not place a live call yet."
