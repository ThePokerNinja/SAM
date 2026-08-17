# Print the latest sam-agent deploy status (no wait). Use when a deploy failed.
#
# Usage (from SAM repo root):
#   $env:RENDER_API_KEY = 'rnd_...'
#   .\scripts\diagnose-sam-deploy.ps1

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_render_sam_agent.ps1")
$creds = Assert-SamAgentRenderCredentials
Write-Host "service=$($creds.ServiceId)" -ForegroundColor Cyan

$deploy = Get-SamAgentLatestDeploy -ServiceId $creds.ServiceId -Headers $creds.Headers
$status = [string]$deploy.status
$deployId = [string]$deploy.id
$commit = ""
if ($deploy.commit -and $deploy.commit.id) {
    $commit = [string]$deploy.commit.id
}
Write-Host "deploy=$deployId status=$status commit=$commit" -ForegroundColor $(if ($status -eq "live") { "Green" } else { "Yellow" })

if ($status -in @("build_failed", "update_failed", "canceled", "deactivated")) {
    Write-Host ""
    Write-Host "Deploy failed on Render. Open the build log:" -ForegroundColor Red
    Write-Host "  https://dashboard.render.com/web/$($creds.ServiceId)/deploys/$deployId" -ForegroundColor White
    Write-Host "Also check Runtime logs on the sam-agent service (update_failed = build OK, startup/health check failed)." -ForegroundColor Yellow
    try {
        $events = Invoke-RenderGet `
            -Uri "https://api.render.com/v1/services/$($creds.ServiceId)/deploys/$deployId/events?limit=20" `
            -Headers $creds.Headers
        $lines = @()
        foreach ($row in $events) {
            $ev = $row.event
            if (-not $ev) { $ev = $row }
            $text = [string]$ev.message
            if (-not $text) { $text = [string]$ev.details }
            if ($text) { $lines += $text }
        }
        if ($lines.Count -gt 0) {
            Write-Host ""
            Write-Host "Recent deploy events:" -ForegroundColor Cyan
            $lines | Select-Object -Last 8 | ForEach-Object { Write-Host "  $_" }
        }
    } catch {
        Write-Host "  (could not fetch deploy events: $($_.Exception.Message))" -ForegroundColor DarkGray
    }
    Write-Host ""
    Write-Host "Common sam-agent failures:" -ForegroundColor Yellow
    Write-Host "  - Docker build timeout (Silero/torch download) -> retry deploy"
    Write-Host "  - pip install OOM on Standard plan -> check requirements.txt"
    Write-Host "  - Bad env var after set-sam-agent-env -> check Environment tab"
    exit 1
}

if ($status -ne "live") {
    Write-Host "Deploy still in progress (status=$status). Re-run with -Wait or watch the dashboard link above."
    exit 2
}

Write-Host "sam-agent deploy is live." -ForegroundColor Green
